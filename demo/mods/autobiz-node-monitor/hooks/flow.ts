import type { EngineInterface } from 'claude-code'

import type { CompleteOn } from '../types'

export type GitRequire = 'commits' | 'clean' | 'merged' | 'pushed'

export type GitOutput = {
  kind: 'git'
  id: string
  repos: string[]
  branch: string
  require: GitRequire[]
}

export type FileOutput = { kind: 'file'; id: string; path: string }

export type FlowNode = {
  id: string
  name: string
  skill: string
  inputs: string[]
  outputs: (GitOutput | FileOutput)[]
  mode: CompleteOn
}

export type Flow = {
  path: string
  featureDir: string
  /** 不算作“未提交改动”的目录：Feature 目录和项目内的配置目录 */
  exclude: string[]
  annotateSkill: boolean
  nodes: FlowNode[]
}

const DEFAULT_REQUIRE: GitRequire[] = ['commits', 'clean', 'merged']

/** 项目内放演示配置和 Feature 产物的目录 */
export const PROJECT_DIR = '.autobiz-demo'
const KNOWN_REQUIRE = new Set<string>(['commits', 'clean', 'merged', 'pushed'])

export const isAbsolute = (p: string) => p.startsWith('/') || /^[A-Za-z]:[\\/]/.test(p)

export const joinPath = (base: string, p: string) => {
  if (isAbsolute(p)) return p
  if (p === '' || p === '.') return base
  return `${base.replace(/[\\/]+$/, '')}/${p.replace(/^\.\//, '')}`
}

/** 技能名去掉插件前缀：`my-plugin:demo-code` → `demo-code`。 */
export const bareSkill = (name: string) => name.slice(name.lastIndexOf(':') + 1)

const asStrings = (v: unknown): string[] =>
  Array.isArray(v) ? v.filter((x): x is string => typeof x === 'string') : typeof v === 'string' ? [v] : []

function parseOutput(id: string, raw: unknown, cwd: string): GitOutput | FileOutput {
  if (typeof raw === 'string') return { kind: 'file', id, path: raw }
  if (Array.isArray(raw)) return { kind: 'file', id, path: String(raw[0] ?? '') }
  const git = (raw as { git?: Record<string, unknown> } | null)?.git
  if (!git || typeof git !== 'object') throw new Error(`产物 ${id} 既不是路径也不是 { "git": {…} }`)
  const reposRaw = git.repos ?? 'project'
  if (reposRaw === 'deployUnits') throw new Error(`产物 ${id}：演示版不支持 repos = "deployUnits"，请写路径数组`)
  const repos = reposRaw === 'project' ? [cwd] : asStrings(reposRaw).map(r => joinPath(cwd, r))
  if (repos.length === 0) throw new Error(`产物 ${id}：repos 为空`)
  const require = git.require === undefined ? DEFAULT_REQUIRE : asStrings(git.require)
  const unknown = require.filter(r => !KNOWN_REQUIRE.has(r))
  if (unknown.length > 0) throw new Error(`产物 ${id}：未知的 require ${unknown.join('、')}`)
  return {
    kind: 'git',
    id,
    repos,
    branch: typeof git.branch === 'string' ? git.branch : 'current',
    require: require as GitRequire[],
  }
}

export async function loadFlow($: EngineInterface, cwd: string): Promise<Flow> {
  // 查找顺序：环境变量 → 项目内 .autobiz-demo/flow.json → 插件自带的 flow.json
  const fromEnv = await $.env.get('AUTOBIZ_NODE_MONITOR_FLOW')
  const inProject = joinPath(cwd, `${PROJECT_DIR}/flow.json`)
  const path = fromEnv ?? ((await $.fs.exists(inProject)) ? inProject : `${$.plugin.root}/flow.json`)
  const text = await $.fs.read(path)
  const raw = JSON.parse(typeof text === 'string' ? text : '') as Record<string, unknown>
  const nodesRaw = Array.isArray(raw.nodes) ? (raw.nodes as Record<string, unknown>[]) : []
  if (nodesRaw.length === 0) throw new Error('nodes 为空')

  const nodes = nodesRaw.map((n, i): FlowNode => {
    const id = typeof n.id === 'string' ? n.id : ''
    const skill = typeof n.skill === 'string' ? n.skill : ''
    if (!id || !skill) throw new Error(`第 ${i + 1} 个节点缺少 id 或 skill`)
    const outputsRaw = (n.outputs ?? {}) as Record<string, unknown>
    const outputs = Object.entries(outputsRaw).map(([oid, o]) => parseOutput(oid, o, cwd))
    const hasGit = outputs.some(o => o.kind === 'git')
    const declared = n.completeOn === 'turnEnd' || n.completeOn === 'handoff' ? n.completeOn : undefined
    return {
      id,
      name: typeof n.name === 'string' ? n.name : id,
      skill: bareSkill(skill),
      inputs: asStrings(n.inputs),
      outputs,
      // §2.8.2：有 git 产物或没有任何产物的节点默认在交接时判断
      mode: declared ?? (hasGit || outputs.length === 0 ? 'handoff' : 'turnEnd'),
    }
  })

  const featureDir = joinPath(cwd, typeof raw.featureDir === 'string' ? raw.featureDir : PROJECT_DIR)
  return {
    path,
    featureDir,
    exclude: [featureDir, joinPath(cwd, PROJECT_DIR)],
    annotateSkill: raw.annotateSkill !== false,
    nodes,
  }
}

export const findBySkill = (flow: Flow, skill: string) =>
  flow.nodes.find(n => n.skill === bareSkill(skill))

export const producerOf = (flow: Flow, artifactId: string) =>
  flow.nodes.find(n => n.outputs.some(o => o.id === artifactId))
