"""Small human projections of Runtime facts; never a source of workflow decisions."""
from pathlib import Path

import sys as _sys  # flowlib bootstrap：插件根目录和 skills/scripts 加入 sys.path
from pathlib import Path as _Path
for _entry in (_Path(__file__).resolve().parents[3], _Path(__file__).resolve().parents[3] / "skills" / "scripts"):
    if str(_entry) not in _sys.path:
        _sys.path.insert(0, str(_entry))
from flowlib.evidence_kernel import FileLock
from flowlib.json_writer_common import write_text


def _cell(value):
    return str(value if value is not None else '').replace('|', '\\|').replace('\n', ' ')


def render_unit_report(feature_dir: Path, feature: str, data: dict) -> Path:
    lines = ['# Unit Test Report', '', f'Feature: {_cell(feature)}',
             f'Verdict: {_cell(data.get("verdict", "BLOCKED"))}', '',
             '| Target | Task | Result | Evidence |', '|---|---|---|---|']
    for row in data.get('targets', []):
        lines.append('| ' + ' | '.join(_cell(value) for value in (row.get('targetId'), row.get('taskId'),
                     row.get('result'), ', '.join(row.get('evidenceIds', [])))) + ' |')
    missing = data.get('unverifiedChecks', [])
    if missing:
        lines.extend(['', '## Unverified'])
        lines.extend('- ' + _cell(row.get('checkId')) + ': ' + _cell(row.get('reasonCode')) for row in missing)
    path = feature_dir / 'UNIT_TEST_REPORT.md'
    write_text(path, '\n'.join(lines) + '\n')
    return path


def render_batch_report(workspace: Path, feature: str, run_id: str) -> Path:
    from flowlib.parallel_runtime import load_manifest, run_dir
    root = run_dir(workspace, feature, run_id)
    path = root / 'validation-summary.md'
    # Read current durable state only after acquiring the view lock so concurrent
    # Batch closures cannot replace a newer projection with an old snapshot.
    with FileLock(root / '.validation-summary.lock'):
        manifest = load_manifest(workspace, feature, run_id)
        lines = ['# Batch validation', '', f'Run: {_cell(run_id)}', '',
                 '| Batch | Review | UTest | Commit |', '|---|---|---|---|']
        for batch_id, batch in sorted(manifest.get('batches', {}).items()):
            states = batch.get('stageStates', {})
            lines.append('| ' + ' | '.join(_cell(value) for value in (batch_id,
                states.get('review', {}).get('status', 'pending'), states.get('test', {}).get('status', 'pending'),
                batch.get('commitSha', ''))) + ' |')
        issues = [row for row in manifest.get('deferredIssues', []) if row.get('status') == 'open']
        if issues:
            lines.extend(['', '## Unresolved'])
            lines.extend('- ' + _cell(row.get('batchId')) + ': ' + _cell(row.get('message') or row.get('failure')) for row in issues)
        write_text(path, '\n'.join(lines) + '\n')
    return path
