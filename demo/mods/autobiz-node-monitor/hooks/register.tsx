import { atom, read } from 'claude-code'
import type { EngineInterface, Register } from 'claude-code'

import type { MonitorEvent, MonitorView, NodeRun, NodeStatus, Readiness, RepoBaseline } from '../types'
import { bareSkill, findBySkill, joinPath, loadFlow, producerOf } from './flow'
import type { Flow, FlowNode } from './flow'
import { checkGit, markDone, rangeOf, short, takeBaseline } from './git'

/**
 * 演示 docs/mods.md §2.3、§2.8：从会话里发生的事推断节点技能的开始和完成。
 * 只监控和提醒，不写任何状态文件；监控记录存在 $.store，按会话目录区分。
 */

const PANE = 'node-monitor'
const PANE_TITLE = '节点监控'
const VIEW = { plugin: 'autobiz-node-monitor', key: 'view' } as const

const EMPTY_VIEW: MonitorView = {
  flowPath: '',
  flowError: null,
  nodes: [],
  current: null,
  readiness: null,
  subagents: 0,
  events: [],
}

const view = atom(VIEW, EMPTY_VIEW)

type Run = {
  nodes: Record<string, NodeRun>
  current: string | null
  readiness: Readiness | null
  events: MonitorEvent[]
}

type Check = { ok: boolean; reasons: string[]; warnings: string[]; summary: string[] }

// 会话级的临时信息：重载后从头开始即可
let cwd = ''
let flow: Flow | null = null
let flowError: string | null = null
const pendingSkill = new Map<string, string | null>()
const subagents = new Set<string>()

let chain: Promise<unknown> = Promise.resolve()
function locked<T>(fn: () => Promise<T>): Promise<T> {
  const run = chain.then(fn)
  chain = run.catch(() => undefined)
  return run
}

const storeKey = () => `run:${cwd}`

async function loadRun($: EngineInterface): Promise<Run> {
  const raw = (await $.store.get(storeKey())) as Partial<Run> | undefined
  return {
    nodes: raw?.nodes ?? {},
    current: raw?.current ?? null,
    readiness: raw?.readiness ?? null,
    events: raw?.events ?? [],
  }
}

async function refreshFlow($: EngineInterface) {
  try {
    flow = await loadFlow($, cwd)
    flowError = null
  } catch (err) {
    flowError = err instanceof Error ? err.message : String(err)
  }
}

const icon = (s: NodeStatus) => (s === 'done' ? '✅' : s === 'in_progress' ? '▶' : '○')

function statusLine(v: MonitorView): string | undefined {
  if (v.flowError) return `节点监控：flow.json 有误`
  const cur = v.nodes.find(n => n.id === v.current)
  if (cur) {
    const r = v.readiness
    const tail = v.subagents > 0
      ? `${v.subagents} 个子代理运行中`
      : r && r.node === cur.id
        ? r.ready ? '可以进入下一步' : r.reasons[0]
        : '进行中'
    return `▶ ${cur.name} · ${tail}`
  }
  if (v.nodes.length > 0 && v.nodes.every(n => n.status === 'done')) return '✅ 流程已全部完成'
  return undefined
}

async function publish($: EngineInterface, run: Run) {
  const v: MonitorView = {
    flowPath: flow?.path ?? '',
    flowError,
    nodes: (flow?.nodes ?? []).map(n => ({
      id: n.id,
      name: n.name,
      skill: n.skill,
      mode: n.mode,
      status: run.nodes[n.id]?.status ?? 'pending',
      repos: run.nodes[n.id]?.repos ?? [],
    })),
    current: run.current,
    readiness: run.readiness,
    subagents: subagents.size,
    events: run.events,
  }
  await $.state.set(VIEW, v)
  $.ui.status(statusLine(v))
}

async function save($: EngineInterface, run: Run) {
  await $.store.set(storeKey(), run)
  await publish($, run)
}

function note(
  $: EngineInterface,
  run: Run,
  level: MonitorEvent['level'],
  text: string,
  how: { toast?: boolean; log?: boolean } = {},
) {
  run.events = [...run.events, { at: Date.now(), level, text }].slice(-30)
  if (how.log !== false) $.ui.log(`[节点监控] ${text}`)
  if (how.toast) $.ui.toast(text)
}

const nodeById = (id: string | null) => (id ? flow?.nodes.find(n => n.id === id) : undefined)
const indexOf = (node: FlowNode) => flow?.nodes.findIndex(n => n.id === node.id) ?? -1

async function checkInputs($: EngineInterface, run: Run, node: FlowNode): Promise<string[]> {
  if (!flow) return []
  const reasons: string[] = []
  for (const id of node.inputs) {
    const producer = producerOf(flow, id)
    const out = producer?.outputs.find(o => o.id === id)
    if (!producer || !out) {
      reasons.push(`输入 ${id} 没有对应的上游产物`)
    } else if (out.kind === 'git') {
      const done = run.nodes[producer.id]
      const ranges = (done?.repos ?? []).filter(r => r.done && r.done !== r.base)
      if (done?.status !== 'done' || ranges.length === 0) {
        reasons.push(`输入 ${id}：“${producer.name}”还没有完成的提交`)
      }
    } else if (!(await $.fs.exists(joinPath(flow.featureDir, out.path)))) {
      reasons.push(`缺少输入 ${out.path}`)
    }
  }
  return reasons
}

async function checkOutputs($: EngineInterface, run: Run, node: FlowNode): Promise<Check> {
  const result: Check = { ok: true, reasons: [], warnings: [], summary: [] }
  if (node.outputs.length === 0) {
    result.summary.push('没有可检查的产物，交接时直接视为完成')
    return result
  }
  const repos = run.nodes[node.id]?.repos ?? []
  for (const out of node.outputs) {
    if (out.kind === 'git') {
      const mine = repos.filter(r => out.repos.includes(r.path))
      if (mine.length === 0) {
        result.reasons.push(`产物 ${out.id} 没有记录到基线（仓库不可用）`)
        continue
      }
      const git = await checkGit($, mine, out.require, flow?.exclude ?? [])
      result.reasons.push(...git.reasons)
      result.warnings.push(...git.warnings)
      result.summary.push(...git.summary)
    } else if (flow) {
      const path = joinPath(flow.featureDir, out.path)
      if (await $.fs.exists(path)) result.summary.push(`${out.path}：已生成`)
      else result.reasons.push(`还没有 ${out.path}`)
    }
  }
  result.ok = result.reasons.length === 0
  return result
}

function setReadiness(run: Run, node: FlowNode, check: Check) {
  run.readiness = {
    node: node.id,
    ready: check.ok,
    reasons: check.reasons,
    warnings: check.warnings,
    summary: check.summary,
    checkedAt: Date.now(),
  }
}

async function startNode($: EngineInterface, run: Run, node: FlowNode): Promise<string[]> {
  const missing = await checkInputs($, run, node)
  if (missing.length > 0) {
    note($, run, 'warn', `“${node.name}”不能开始：${missing.join('；')}`, { toast: true })
    return missing
  }
  const repos: RepoBaseline[] = []
  const errors: string[] = []
  for (const out of node.outputs) {
    if (out.kind !== 'git') continue
    const b = await takeBaseline($, out)
    repos.push(...b.repos)
    errors.push(...b.errors)
  }
  run.nodes[node.id] = { status: 'in_progress', startedAt: Date.now(), repos }
  run.current = node.id
  run.readiness = null
  const base = repos.map(r => `${r.key}@${r.branch} ${short(r.base)}`).join('，')
  note($, run, 'info', `▶ “${node.name}”开始${base ? `，基线 ${base}` : ''}`, { toast: true })
  if (errors.length > 0) note($, run, 'warn', `基线有问题：${errors.join('；')}`, { toast: true })
  void $.ui.open({ id: PANE, title: PANE_TITLE })
  return []
}

/** 交接或每轮结束时判定完成；通过就记下完成时的 HEAD。 */
async function finishNode($: EngineInterface, run: Run, node: FlowNode, trigger: string): Promise<boolean> {
  const check = await checkOutputs($, run, node)
  setReadiness(run, node, check)
  if (!check.ok) {
    note($, run, 'warn', `“${node.name}”还没完成（${trigger}）：${check.reasons.join('；')}`, { toast: true })
    return false
  }
  const prev = run.nodes[node.id] ?? { status: 'in_progress' as const }
  const repos = await markDone($, prev.repos ?? [])
  run.nodes[node.id] = { ...prev, status: 'done', doneAt: Date.now(), repos }
  run.current = null
  run.readiness = null
  const ranges = repos.map(r => `${r.key} ${rangeOf(r)}`).join('，')
  note($, run, 'ok', `✅ “${node.name}”完成（${trigger}）${ranges ? `，提交范围 ${ranges}` : ''}`, { toast: true })
  return true
}

/** 只查产物、不改状态；结果变化时提醒一次。 */
async function precheck($: EngineInterface, run: Run, node: FlowNode): Promise<boolean> {
  const before = run.readiness
  const check = await checkOutputs($, run, node)
  setReadiness(run, node, check)
  const changed =
    !before ||
    before.node !== node.id ||
    before.ready !== check.ok ||
    before.reasons.join('|') !== check.reasons.join('|')
  if (changed) {
    if (check.ok) {
      const next = flow?.nodes[indexOf(node) + 1]
      const hint = node.mode === 'handoff'
        ? next ? `，调用“${next.name}”（/${next.skill}）时判定完成` : '，可以用 /node-monitor done 标记完成'
        : ''
      note($, run, 'ok', `“${node.name}”的产物已齐全${hint}`, { toast: true })
    } else {
      note($, run, 'info', `“${node.name}”预检查：${check.reasons.join('；')}`)
    }
  }
  return check.ok
}

/** 节点技能展开时：开始、继续、交接，或说明为什么不能开始。返回附在技能正文后的说明。 */
async function onSkill($: EngineInterface, run: Run, node: FlowNode, isMain: boolean): Promise<string[]> {
  const blocked: string[] = []
  const status = run.nodes[node.id]?.status ?? 'pending'
  const current = nodeById(run.current)
  const i = indexOf(node)

  if (current && current.id === node.id) {
    note($, run, 'info', `“${node.name}”继续（技能再次调用）`, { log: false })
  } else if (current) {
    if (isMain && i === indexOf(current) + 1) {
      const ok = await finishNode($, run, current, '调用下一节点的技能')
      if (ok) blocked.push(...(await startNode($, run, node)))
      else blocked.push(...(run.readiness?.reasons ?? []).map(r => `上一步“${current.name}”还没完成：${r}`))
    } else if (!isMain) {
      note($, run, 'info', `子代理调用了“${node.name}”的技能，不触发交接（当前节点“${current.name}”）`)
    } else {
      const why = `当前节点是“${current.name}”，“${node.name}”不是它的下一步`
      blocked.push(why)
      note($, run, 'warn', why, { toast: true })
    }
  } else if (status === 'done') {
    note($, run, 'info', `“${node.name}”已经完成，再次调用不会重开（/node-monitor reset 可以重来）`)
  } else {
    const prev = i > 0 ? flow?.nodes[i - 1] : undefined
    if (prev && run.nodes[prev.id]?.status !== 'done') {
      blocked.push(`前一步“${prev.name}”还没完成`)
      note($, run, 'warn', `“${node.name}”不能开始：前一步“${prev.name}”还没完成`, { toast: true })
    } else {
      blocked.push(...(await startNode($, run, node)))
    }
  }
  return blocked
}

/** R2 的演示：把产物约定附在技能正文后（不含任何状态操作）。 */
function contract(run: Run, node: FlowNode, blocked: string[]): string {
  if (!flow) return ''
  const lines = ['---', `（autobiz-node-monitor 附加：本节点“${node.name}”的产物约定）`]
  for (const id of node.inputs) {
    const producer = producerOf(flow, id)
    const out = producer?.outputs.find(o => o.id === id)
    if (!producer || !out) continue
    if (out.kind === 'git') {
      const ranges = (run.nodes[producer.id]?.repos ?? []).map(r => `${r.path}（${r.branch}）${rangeOf(r)}`)
      lines.push(`- 输入 ${id}：上一步的代码提交 ${ranges.join('；') || '（暂无）'}`)
    } else {
      lines.push(`- 输入 ${id}：${joinPath(flow.featureDir, out.path)}`)
    }
  }
  for (const out of node.outputs) {
    if (out.kind === 'git') {
      const branch = out.branch === 'current' ? '当前分支' : `分支 ${out.branch}`
      lines.push(`- 输出 ${out.id}：在 ${out.repos.join('、')} 中提交代码到${branch}；用了独立工作树的要合并回来`)
    } else {
      lines.push(`- 输出 ${out.id}：写到 ${joinPath(flow.featureDir, out.path)}`)
    }
  }
  if (blocked.length > 0) {
    lines.push('', '注意：这一步现在还不能开始，请先处理或告诉用户：', ...blocked.map(b => `- ${b}`))
  }
  return lines.join('\n')
}

async function statusText($: EngineInterface): Promise<string> {
  const run = await loadRun($)
  if (flowError) return `flow.json 有误：${flowError}\n配置文件：${flow?.path ?? '（未读到）'}`
  const lines = (flow?.nodes ?? []).map(n => {
    const s = run.nodes[n.id]?.status ?? 'pending'
    return `${icon(s)} ${n.name}（/${n.skill}，${n.mode === 'handoff' ? '交接时判断' : '每轮结束判断'}）`
  })
  const r = run.readiness
  if (r) {
    lines.push('', r.ready ? '预检查：产物已齐全' : `预检查：${r.reasons.join('；')}`)
    lines.push(...r.summary.map(s => `  ${s}`), ...r.warnings.map(w => `  ⚠ ${w}`))
  }
  if (subagents.size > 0) lines.push(`子代理：${subagents.size} 个在运行`)
  return lines.join('\n')
}

async function checkNow($: EngineInterface): Promise<string> {
  return locked(async () => {
    await refreshFlow($)
    const run = await loadRun($)
    const node = nodeById(run.current)
    if (!node) {
      await publish($, run)
      return '当前没有进行中的节点。'
    }
    const ok = await precheck($, run, node)
    if (ok && node.mode === 'turnEnd') await finishNode($, run, node, '手动检查')
    await save($, run)
    return ok ? `“${node.name}”的产物已齐全。` : `“${node.name}”还差：${run.readiness?.reasons.join('；')}`
  })
}

async function markNow($: EngineInterface): Promise<string> {
  return locked(async () => {
    await refreshFlow($)
    const run = await loadRun($)
    const node = nodeById(run.current)
    if (!node) return '当前没有进行中的节点。'
    const ok = await finishNode($, run, node, '手动标记')
    await save($, run)
    return ok ? `“${node.name}”已标记完成。` : `“${node.name}”还不能完成：${run.readiness?.reasons.join('；')}`
  })
}

const time = (ms: number) => {
  const d = new Date(ms)
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    const started = await next(e)
    cwd = e.cwd
    await $.command.register({
      name: 'node-monitor',
      description: '节点监控：status（默认）、open、check、done、reset',
      argumentHint: 'status | open | check | done | reset',
    })
    await refreshFlow($)
    const run = await loadRun($)
    await publish($, run)
    if (run.current || flowError) void $.ui.open({ id: PANE, title: PANE_TITLE })
    return started
  })

  // 记下这次 Skill 工具调用来自主会话还是子代理，skill.prompt 里要用
  on('tool.call', { tool: 'Skill' }, async ($, e, next) => {
    const bare = bareSkill(e.skill)
    pendingSkill.set(bare, e.agentId ?? null)
    try {
      return await next(e)
    } finally {
      pendingSkill.delete(bare)
    }
  }).catch(($, e, next) => next(e))

  on('skill.prompt', async ($, e, next) => {
    const expanded = await next(e)
    await refreshFlow($)
    const node = flow ? findBySkill(flow, e.skill) : undefined
    if (!node) return expanded
    // 斜杠命令没有 Skill 工具调用，一定来自主会话
    const isMain = !pendingSkill.get(bareSkill(e.skill))
    const extra = await locked(async () => {
      const run = await loadRun($)
      const blocked = await onSkill($, run, node, isMain)
      await save($, run)
      return flow?.annotateSkill ? contract(run, node, blocked) : ''
    })
    return extra ? { ...expanded, text: `${expanded.text}\n\n${extra}` } : expanded
  })

  on('turn.start', async ($, e, next) => {
    if (e.agentId) {
      subagents.add(e.agentId)
      await publish($, await loadRun($))
    }
    return next(e)
  })

  on('turn.complete', async ($, e, next) => {
    const done = await next(e)
    if (e.agentId) {
      subagents.delete(e.agentId)
      await publish($, await loadRun($))
      return done
    }
    if (e.reason !== 'answer') return done
    await locked(async () => {
      await refreshFlow($)
      const run = await loadRun($)
      const node = nodeById(run.current)
      if (!node) return publish($, run)
      if (subagents.size > 0) {
        note($, run, 'info', `还有 ${subagents.size} 个子代理在运行，等它们结束再检查“${node.name}”`, { log: false })
        return save($, run)
      }
      const ready = await precheck($, run, node)
      if (ready && node.mode === 'turnEnd') await finishNode($, run, node, '一轮结束')
      return save($, run)
    })
    return done
  })

  on('session.end', async ($, e, next) => {
    await locked(async () => {
      if (!flow) return
      const run = await loadRun($)
      const node = nodeById(run.current)
      if (node?.mode !== 'handoff') return
      await finishNode($, run, node, '会话结束')
      await $.store.set(storeKey(), run)
    })
    return next(e)
  })

  on('command.run', { command: 'node-monitor' }, async ($, e) => {
    const arg = e.args.trim().split(/\s+/)[0] || 'status'
    if (arg === 'open') {
      await $.ui.open({ id: PANE, title: PANE_TITLE })
      return { text: '已打开节点监控面板。' }
    }
    if (arg === 'check') return { text: await checkNow($) }
    if (arg === 'done') return { text: await markNow($) }
    if (arg === 'reset') {
      await locked(async () => {
        await $.store.delete(storeKey())
        await publish($, await loadRun($))
      })
      return { text: '监控记录已清空。' }
    }
    await refreshFlow($)
    return { text: await statusText($) }
  })

  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const { Box, Text, Button } = $.ui.resolve(e)
    const v = await read($, view)
    const cur = v.nodes.find(n => n.id === v.current)
    const r = v.readiness && cur && v.readiness.node === cur.id ? v.readiness : null
    const room = Math.max(3, (e.viewport?.rows ?? 30) - 18 - v.nodes.length)

    return (
      <Box flexDirection="column" gap={1}>
        {v.flowError && <Text color="error">flow.json 有误：{v.flowError}</Text>}

        <Box flexDirection="column">
          <Text weight="bold">流程</Text>
          {v.nodes.map(n => (
            <Box flexDirection="row" gap={1}>
              <Text color={n.status === 'done' ? 'success' : n.status === 'in_progress' ? 'suggestion' : undefined} dimColor={n.status === 'pending'}>
                {icon(n.status)} {n.name}
              </Text>
              <Text dimColor>/{n.skill} · {n.mode === 'handoff' ? '交接时判断' : '每轮结束判断'}</Text>
            </Box>
          ))}
        </Box>

        {cur ? (
          <Box flexDirection="column">
            <Text weight="bold">当前：{cur.name}</Text>
            {cur.repos.map(b => (
              <Text dimColor>基线 {b.key} · {b.branch} · {short(b.base)}</Text>
            ))}
            {v.subagents > 0 && <Text color="warning">{v.subagents} 个子代理在运行，结束后再检查</Text>}
            {r === null && <Text dimColor>还没有检查过；每轮结束后自动检查</Text>}
            {r && r.ready && <Text color="success">✅ 产物已齐全{cur.mode === 'handoff' ? '，进入下一步时判定完成' : ''}</Text>}
            {r && !r.ready && r.reasons.map(reason => <Text color="warning">⚠ {reason}</Text>)}
            {r && r.summary.map(s => <Text dimColor>{s}</Text>)}
            {r && r.warnings.map(w => <Text color="warning">注意：{w}</Text>)}
            <Box flexDirection="row" gap={1}>
              <Button key="check" label="立即检查" onPress={() => void checkNow($)} />
              <Button key="done" label="标记完成" variant="primary" onPress={() => void markNow($)} />
            </Box>
          </Box>
        ) : (
          <Text dimColor>
            {v.nodes.length > 0 && v.nodes.every(n => n.status === 'done')
              ? '流程已全部完成。'
              : '当前没有进行中的节点；调用流程中下一个节点的技能即开始。'}
          </Text>
        )}

        <Box flexDirection="column">
          <Text weight="bold">最近事件</Text>
          {v.events.length === 0 && <Text dimColor>（无）</Text>}
          {v.events.slice(-room).map(ev => (
            <Text color={ev.level === 'ok' ? 'success' : ev.level === 'warn' ? 'warning' : undefined} dimColor={ev.level === 'info'}>
              {time(ev.at)} {ev.text}
            </Text>
          ))}
        </Box>

        <Text dimColor>配置：{v.flowPath || '（未读到）'}</Text>
      </Box>
    )
  })
}
