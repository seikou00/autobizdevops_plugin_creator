export type NodeStatus = 'pending' | 'in_progress' | 'done'

export type CompleteOn = 'turnEnd' | 'handoff'

/** 节点开始时记下的一个仓库的基线（docs/mods.md §2.8.1）。 */
export type RepoBaseline = {
  key: string
  path: string
  branch: string
  base: string
  worktrees: string[]
  done: string | null
}

export type NodeRun = {
  status: NodeStatus
  startedAt?: number
  doneAt?: number
  repos?: RepoBaseline[]
}

export type Readiness = {
  node: string
  ready: boolean
  reasons: string[]
  warnings: string[]
  summary: string[]
  checkedAt: number
}

export type MonitorEvent = {
  at: number
  level: 'info' | 'ok' | 'warn'
  text: string
}

export type ViewNode = {
  id: string
  name: string
  skill: string
  mode: CompleteOn
  status: NodeStatus
  repos: RepoBaseline[]
}

export type MonitorView = {
  flowPath: string
  flowError: string | null
  nodes: ViewNode[]
  current: string | null
  readiness: Readiness | null
  subagents: number
  events: MonitorEvent[]
}

declare module 'claude-code' {
  interface PluginState {
    'autobiz-node-monitor': { view: MonitorView }
  }
}
