import { expect, mock, test } from 'claude-code/testing'
import type { On } from 'claude-code'

import type { NodeRun, Readiness } from '../types'

const REPO = '/proj/repo'
const FEATURE = '/proj/feature'

const FLOW = {
  featureDir: FEATURE,
  nodes: [
    {
      id: 'dev.code',
      name: '增量编码',
      skill: 'demo-code',
      outputs: { code: { git: { repos: [REPO] } } },
    },
    {
      id: 'dev.review',
      name: '代码评审',
      skill: 'demo-review',
      inputs: ['code'],
      outputs: { review: 'REVIEW.md' },
    },
  ],
}

type Run = { nodes: Record<string, NodeRun>; current: string | null; readiness: Readiness | null }

type Repo = { head: string; commits: number; dirty: string[]; worktree: { ahead: number } | null }

/** 这里的每个 hook 都代表引擎：假的 git、文件和界面。 */
function engine(on: On, repo: Repo, files: Set<string>, toasts: string[], store: Map<string, unknown>) {
  on('store.get', (_, e) => ({ value: store.get(e.key) }))
  on('store.set', (_, e) => {
    store.set(e.key, JSON.parse(JSON.stringify(e.value)))
    return { value: undefined }
  })
  on('store.delete', (_, e) => {
    store.delete(e.key)
    return { value: undefined }
  })
  mock.env(on, {})
  on('command.register', () => ({ value: { command: 'node-monitor' } }))
  on('ui.open', () => ({ value: { isPlaced: true } }))
  on('ui.toast', (_, e) => {
    toasts.push(e.text)
    return { value: undefined }
  })
  on('ui.status', () => ({ value: undefined }))
  on('ui.log', () => ({ value: undefined }))
  on('fs.read', () => ({ value: JSON.stringify(FLOW) }))
  on('fs.exists', (_, e) => ({ value: files.has(e.path) }))
  on('process.run', (_, e) => {
    const args = e.argv.slice(1).join(' ')
    const ok = (stdout: string) => ({
      value: { exitCode: 0, stdout, stderr: '', isStdoutTruncated: false, isStderrTruncated: false },
    })
    if (args === 'rev-parse --show-toplevel') return ok(REPO)
    if (args === 'rev-parse --abbrev-ref HEAD') return ok('main')
    if (args === 'rev-parse --verify --quiet main') return ok(repo.head)
    if (args === 'worktree list --porcelain') {
      const extra = repo.worktree ? `\n\nworktree /tmp/wt\nHEAD bbbbbbb\nbranch refs/heads/agent-1` : ''
      return ok(`worktree ${REPO}\nHEAD ${repo.head}\nbranch refs/heads/main${extra}`)
    }
    if (args.startsWith('rev-list --count main..refs/heads/agent-1')) return ok(String(repo.worktree?.ahead ?? 0))
    if (args.startsWith('rev-list --count')) return ok(String(repo.commits))
    if (args.startsWith('status --porcelain')) return ok(repo.dirty.join('\n'))
    return ok('')
  })
  on('session.start', (_, e) => ({ cwd: e.cwd }))
  on('skill.prompt', (_, e) => ({ text: e.text }))
  on('turn.start', (_, e) => ({ turnId: e.turnId }))
  on('turn.complete', (_, e) => ({ text: e.answer }))
  on('tool.call', () => ({ result: {} }))
}

const turnEnd = (agentId?: string) => ({
  answer: '',
  durationMs: 1,
  isAborted: false,
  turnId: agentId ? `t-${agentId}` : 't-main',
  reason: 'answer' as const,
  ...(agentId ? { agentId } : {}),
})

test('编码节点：技能开始、预检查、等子代理、交接时完成', async ($, on) => {
  const repo: Repo = { head: 'aaaaaaa1111', commits: 0, dirty: [], worktree: null }
  const files = new Set<string>()
  const toasts: string[] = []
  const store = new Map<string, unknown>()
  const run = () => store.get('run:/proj') as Run
  engine(on, repo, files, toasts, store)

  await $.session.start({ cwd: '/proj', surface: 'desktop', isInteractive: true })

  // 1. 斜杠命令调用编码技能：节点开始，记下基线，正文后附上产物约定
  const code = await $.skill.prompt({ skill: 'demo-code', text: 'BODY' })
  expect(code.text).toContain('产物约定')
  expect(code.text).toContain(REPO)
  expect(run().current).toBe('dev.code')
  expect(run().nodes['dev.code']?.repos?.[0]?.base).toBe('aaaaaaa1111')
  expect(toasts.some(t => t.includes('开始'))).toBe(true)

  // 2. 一轮结束，还没有提交
  await $.turn.complete(turnEnd())
  expect(run().readiness?.reasons).toContain('还没有新提交')

  // 3. 有提交，但有未提交的文件，还有子代理的工作树没合并
  repo.commits = 2
  repo.head = 'ccccccc2222'
  repo.dirty = [' M app.py']
  repo.worktree = { ahead: 1 }
  await $.turn.complete(turnEnd())
  expect(run().readiness?.reasons.join('；')).toContain('1 个文件未提交')
  expect(run().readiness?.reasons.join('；')).toContain('未合并')

  // 4. 子代理还在跑：主会话这轮结束不检查
  repo.dirty = []
  repo.worktree = { ahead: 0 }
  await $.turn.start({ text: 'sub', turnId: 't-a1', agentId: 'a1' })
  await $.turn.complete(turnEnd())
  expect(run().readiness?.ready).toBe(false)

  // 5. 子代理结束，下一轮结束时产物齐全
  await $.turn.complete(turnEnd('a1'))
  await $.turn.complete(turnEnd())
  expect(run().readiness?.ready).toBe(true)
  expect(run().nodes['dev.code']?.status).toBe('in_progress')

  // 6. 调用下一个节点的技能：交接，编码完成，评审开始，评审拿到提交范围
  const review = await $.skill.prompt({ skill: 'demo-review', text: 'BODY' })
  expect(run().nodes['dev.code']?.status).toBe('done')
  expect(run().current).toBe('dev.review')
  expect(review.text).toContain('aaaaaaa..ccccccc')

  // 7. 评审是文件产物，每轮结束判断：写出 REVIEW.md 后这一轮结束即完成
  files.add(`${FEATURE}/REVIEW.md`)
  await $.turn.complete(turnEnd())
  expect(run().nodes['dev.review']?.status).toBe('done')
  expect(run().current).toBe(null)

  // 面板在每个界面上都能画出来
  for (const surface of ['terminal', 'desktop', 'vscode', 'mobile'] as const) {
    const ui = await $.ui.mount({
      plugin: 'autobiz-node-monitor',
      component: 'Pane',
      requestId: 'node-monitor',
      surface,
      props: {
        title: '节点监控',
        isFocused: false,
        bodyColumns: 60,
        placement: 'dock',
        scroll: { offset: 0, bodyRows: 30 },
        view: {},
      },
    })
    expect(await ui.find({ type: 'Text', text: /代码评审/ })).toBeDefined()
    expect(await ui.find({ type: 'Text', text: /流程已全部完成/ })).toBeDefined()
    await ui.unmount()
  }
})

test('交接时编码没做完：评审不开始，原因附在评审技能正文后', async ($, on) => {
  const repo: Repo = { head: 'aaaaaaa1111', commits: 1, dirty: ['?? notes.txt'], worktree: null }
  const toasts: string[] = []
  const store = new Map<string, unknown>()
  engine(on, repo, new Set(), toasts, store)

  await $.session.start({ cwd: '/proj2', surface: 'terminal', isInteractive: true })
  await $.skill.prompt({ skill: 'demo-code', text: 'BODY' })

  const review = await $.skill.prompt({ skill: 'demo-review', text: 'BODY' })
  expect(review.text).toContain('还不能开始')
  expect(review.text).toContain('notes.txt')
  const saved = store.get('run:/proj2') as Run
  expect(saved.current).toBe('dev.code')
  expect(saved.nodes['dev.review']).toBeUndefined()
  expect(toasts.some(t => t.includes('还没完成'))).toBe(true)
})
