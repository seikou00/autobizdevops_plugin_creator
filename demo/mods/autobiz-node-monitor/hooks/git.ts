import type { EngineInterface } from 'claude-code'

import type { RepoBaseline } from '../types'
import type { GitOutput, GitRequire } from './flow'

type Git = { ok: boolean; out: string; err: string }

async function git($: EngineInterface, cwd: string, args: string[]): Promise<Git> {
  try {
    const r = await $.process.run(['git', ...args], { cwd, timeoutMs: 15_000 })
    return { ok: r.exitCode === 0, out: r.stdout.trim(), err: r.stderr.trim() }
  } catch (err) {
    return { ok: false, out: '', err: String(err) }
  }
}

export const short = (sha: string | null | undefined) => (sha ? sha.slice(0, 7) : '（无）')

const repoKey = (path: string) => path.replace(/[\\/]+$/, '').split(/[\\/]/).pop() || path

type Worktree = { path: string; ref: string }

async function worktrees($: EngineInterface, cwd: string): Promise<Worktree[]> {
  const r = await git($, cwd, ['worktree', 'list', '--porcelain'])
  if (!r.ok) return []
  return r.out
    .split(/\n\s*\n/)
    .map(block => {
      const lines = block.split('\n')
      const path = lines.find(l => l.startsWith('worktree '))?.slice(9) ?? ''
      const branch = lines.find(l => l.startsWith('branch '))?.slice(7)
      const head = lines.find(l => l.startsWith('HEAD '))?.slice(5) ?? ''
      return { path, ref: branch ?? head }
    })
    .filter(w => w.path)
}

/** 节点开始时为一个 git 产物的全部仓库记下基线。 */
export async function takeBaseline(
  $: EngineInterface,
  output: GitOutput,
): Promise<{ repos: RepoBaseline[]; errors: string[] }> {
  const repos: RepoBaseline[] = []
  const errors: string[] = []
  for (const path of output.repos) {
    const key = repoKey(path)
    const top = await git($, path, ['rev-parse', '--show-toplevel'])
    if (!top.ok) {
      errors.push(`${key}：${path} 不是 git 仓库`)
      continue
    }
    const current = await git($, path, ['rev-parse', '--abbrev-ref', 'HEAD'])
    const branch = output.branch === 'current' ? current.out || 'HEAD' : output.branch
    const head = await git($, path, ['rev-parse', '--verify', '--quiet', branch])
    repos.push({
      key,
      path,
      branch,
      base: head.ok ? head.out : '',
      worktrees: (await worktrees($, path)).map(w => w.path),
      done: null,
    })
  }
  return { repos, errors }
}

export type GitCheck = {
  ok: boolean
  reasons: string[]
  warnings: string[]
  summary: string[]
}

/** 按 §2.8.1 的齐全条件检查一个 git 产物。 */
export async function checkGit(
  $: EngineInterface,
  repos: RepoBaseline[],
  require: GitRequire[],
  exclude: string[] = [],
): Promise<GitCheck> {
  const reasons: string[] = []
  const warnings: string[] = []
  const summary: string[] = []
  let totalCommits = 0

  for (const b of repos) {
    const current = await git($, b.path, ['rev-parse', '--abbrev-ref', 'HEAD'])
    if (current.ok && current.out !== b.branch) {
      warnings.push(`${b.key} 当前在 ${current.out}，开始时在 ${b.branch}，提交可能落在了别的分支上`)
    }

    const head = await git($, b.path, ['rev-parse', '--verify', '--quiet', b.branch])
    const range = b.base ? `${b.base}..${b.branch}` : b.branch
    const count = await git($, b.path, ['rev-list', '--count', range, '--', '.'])
    const commits = count.ok ? Number(count.out) || 0 : 0
    totalCommits += commits
    summary.push(`${b.key}：${b.branch} ${short(b.base)}..${short(head.out)}，${commits} 个新提交`)

    if (require.includes('clean')) {
      const root = b.path.replace(/[\\/]+$/, '')
      const skip = exclude
        .filter(p => p.startsWith(`${root}/`))
        .map(p => `:(exclude)${p.slice(root.length + 1)}`)
      const status = await git($, b.path, ['status', '--porcelain', '--untracked-files=normal', '--', '.', ...skip])
      const files = status.out ? status.out.split('\n').map(l => l.slice(3)) : []
      if (files.length > 0) {
        const shown = files.slice(0, 20).join('、')
        reasons.push(`${b.key} 有 ${files.length} 个文件未提交：${shown}${files.length > 20 ? ' …' : ''}`)
      }
    }

    if (require.includes('merged')) {
      for (const w of await worktrees($, b.path)) {
        if (b.worktrees.includes(w.path) || !w.ref) continue
        const ahead = await git($, b.path, ['rev-list', '--count', `${b.branch}..${w.ref}`])
        const n = ahead.ok ? Number(ahead.out) || 0 : 0
        if (n > 0) {
          const name = w.ref.replace(/^refs\/heads\//, '')
          reasons.push(`${b.key} 的工作树 ${w.path}（${name}）有 ${n} 个提交未合并回 ${b.branch}`)
        }
      }
    }

    if (require.includes('pushed')) {
      const up = await git($, b.path, ['rev-list', '--count', `${b.branch}@{u}..${b.branch}`])
      if (!up.ok) reasons.push(`${b.key} 的 ${b.branch} 没有上游分支，无法确认是否已推送`)
      else if (Number(up.out) > 0) reasons.push(`${b.key} 有 ${up.out} 个提交未推送`)
    }
  }

  if (require.includes('commits') && totalCommits === 0) reasons.unshift('还没有新提交')

  return { ok: reasons.length === 0, reasons, warnings, summary }
}

/** 节点完成时记下各仓库的 HEAD，作为下游节点的提交范围。 */
export async function markDone($: EngineInterface, repos: RepoBaseline[]): Promise<RepoBaseline[]> {
  const out: RepoBaseline[] = []
  for (const b of repos) {
    const head = await git($, b.path, ['rev-parse', '--verify', '--quiet', b.branch])
    out.push({ ...b, done: head.ok ? head.out : null })
  }
  return out
}

export const rangeOf = (b: RepoBaseline) => `${short(b.base)}..${short(b.done)}`
