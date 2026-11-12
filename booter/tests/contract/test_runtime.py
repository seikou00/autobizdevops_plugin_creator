"""运行框架的契约测试：在临时工作区按宿主的方式调用生成的插件（interfaces.md §3、§4）。

看板事件推送用一个模拟的 DevClaw 服务验证（interfaces.md §3.5.3）。
"""

import http.server
import json
import os
import subprocess
import sys
import threading
import unittest
from pathlib import Path

from tests.helpers import built_example, run_script, temp_dir

INSPECT = "runtime/adapters/inspect_state.py"
UPDATE = "runtime/workflow/update_state.py"
GUARD = "hooks/artifact_guard.py"


class Workspace:
    def __init__(self, test, example="minimal"):
        self.test = test
        self.plugin = built_example(test, example)
        self.root = temp_dir(test) / "ws"
        (self.root / "p1").mkdir(parents=True)
        self.meta = self.root / "p1" / ".autobizdevops"

    def host(self, script, *args, env=None):
        return run_script(self.plugin, script, *args, env=env)

    def create(self, feature="f1", env=None):
        code, payload, _ = self.host("runtime/adapters/init_feature.py", "--workspace", str(self.root), "--project", "p1",
                                     "--feature", feature, "--selected-deployUnit", "[]", env=env)
        self.test.assertEqual(code, 0, payload)
        return payload

    def update(self, checkpoint, *extra, feature="f1", env=None):
        environment = {"PLUGIN_WORKSPACE": str(self.root), "PROJECT_DIR": "p1", "FEATURE_ID": feature, **(env or {})}
        return self.host(UPDATE, "--feature", feature, "--checkpoint", checkpoint, *extra, env=environment)

    def guard(self, command, feature="f1"):
        """按宿主 PreToolUse 钩子的方式调用产物检查钩子，返回 (退出码, stdout 的 JSON 或 None)。"""
        payload = json.dumps({"tool_name": "execute", "tool_input": {"command": command}})
        environment = {**os.environ, "PLUGIN_WORKSPACE": str(self.root), "PROJECT_DIR": "p1", "FEATURE_ID": feature,
                       "PYTHONDONTWRITEBYTECODE": "1"}
        completed = subprocess.run([sys.executable, "-X", "utf8", str(self.plugin / GUARD)], input=payload.encode(),
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=environment)
        out = completed.stdout.decode("utf-8").strip()
        return completed.returncode, json.loads(out) if out else None

    def write(self, rel, text="内容\n", feature="f1"):
        path = self.meta / "features" / feature / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def run(self, feature="f1"):
        code, payload, _ = self.host(INSPECT, "--mode", "run", "--workspace", str(self.root), "--project", "p1",
                                     "--feature", feature)
        self.test.assertEqual(code, 0, payload)
        return payload["run"]

    def flow(self):
        return json.loads((self.plugin / "runtime/config/flow.json").read_text("utf-8"))

    def set_flow(self, flow):
        (self.plugin / "runtime/config/flow.json").write_text(json.dumps(flow, ensure_ascii=False), "utf-8")


class StateTest(unittest.TestCase):
    def test_missing_outputs_warn_but_do_not_block(self):
        ws = Workspace(self)
        ws.create()
        code, payload, _ = ws.update("draft_done", "--dry-run")
        self.assertEqual(code, 0, payload)
        self.assertIn("推进到 draft_done 时必需产物缺失: DRAFT.md", payload["warnings"])
        ws.write("DRAFT.md", "  \n")
        code, payload, _ = ws.update("draft_done")
        self.assertEqual(code, 0, payload)
        self.assertEqual(payload["checkpoint"], "draft_done")
        self.assertTrue(any("为空" in warning for warning in payload["warnings"]))
        events = [json.loads(line) for line in (ws.meta / "hooks.ndjson").read_text("utf-8").splitlines()]
        self.assertEqual([event["eventId"] for event in events], ["artifact-check", "update-state"])
        self.assertEqual(events[0]["eventStatus"], "warning")

    def test_guard_hook_blocks_done_command_until_outputs_exist(self):
        ws = Workspace(self)
        ws.create()
        done = f'python -X utf8 "{ws.plugin / UPDATE}" --feature "f1" --checkpoint draft_done'
        code, payload = ws.guard(done)
        self.assertEqual(code, 2)
        self.assertEqual(payload["decision"], "block")
        self.assertIn("必需产物缺失: DRAFT.md", payload["reason"])
        ws.write("DRAFT.md", "  \n")
        code, payload = ws.guard(f"bash -lc 'cd /tmp && {done}'")
        self.assertEqual(code, 2)
        self.assertIn("必需产物为空: DRAFT.md", payload["reason"])
        for command in ("ls -la", done.replace("draft_done", "draft_in_progress"), done + " --dry-run"):
            self.assertEqual(ws.guard(command), (0, None), command)
        ws.write("DRAFT.md")
        self.assertEqual(ws.guard(done), (0, None))
        ws.update("draft_done")
        self.assertEqual(ws.guard(done), (0, None))

    def test_linear_flow_advances_and_rejects_skipping(self):
        ws = Workspace(self)
        created = ws.create()
        self.assertEqual(created["checkpoint"], "draft_in_progress")
        self.assertFalse(ws.create()["created"])
        ws.write("DRAFT.md")
        self.assertEqual(ws.update("draft_done")[0], 0)
        code, payload, _ = ws.update("review_done")
        self.assertEqual(code, 1)
        self.assertIn("不允许状态跳转", payload["errors"][0])
        self.assertEqual(ws.update("review_in_progress")[0], 0)
        run = ws.run()
        self.assertEqual([node["nodeStatus"] for node in run["nodes"]], ["done", "in_progress"])
        self.assertEqual(run["nodes"][0]["artifacts"][0]["artifactStatus"], "generated")
        events = [json.loads(line) for line in (ws.meta / "hooks.ndjson").read_text("utf-8").splitlines()]
        self.assertEqual([event["to"] for event in events], ["draft_done", "review_in_progress"])
        self.assertTrue(all(event["pluginId"] == "doc-review" for event in events))

    def test_reopen_needs_reason_and_goes_back(self):
        ws = Workspace(self)
        ws.create()
        ws.write("DRAFT.md")
        ws.update("draft_done")
        ws.update("review_in_progress")
        self.assertEqual(ws.update("draft_in_progress", "--reopen")[0], 1)
        code, payload, _ = ws.update("draft_in_progress", "--reopen", "--reason", "补充需求")
        self.assertEqual(code, 0, payload)
        self.assertEqual(ws.run()["currentNodeId"], "draft")

    def test_terminal_node_archives_and_locks(self):
        ws = Workspace(self, "fullstack")
        ws.create()
        flow = ws.flow()
        for node in flow["nodes"][:-1]:
            self.assertEqual(ws.update(node["checkpoints"][0])[0], 0, node["id"])
            for ref in node["outputs"]:
                if ref["required"]:
                    pattern = flow["artifacts"][ref["id"]]["paths"][0]
                    ws.write(pattern.replace("**", "demo").replace("*", "demo"))
            code, payload, _ = ws.update(node["checkpoints"][1])
            self.assertEqual(code, 0, payload)
        self.assertEqual(ws.update("archived")[0], 0)
        self.assertEqual(ws.run()["nodes"][-1]["nodeStatus"], "archived")
        code, payload, _ = ws.update("prd_in_progress", "--reopen", "--reason", "x")
        self.assertEqual(code, 1)
        self.assertIn("已归档", payload["errors"][0])

    def test_state_of_another_plugin_is_refused(self):
        ws = Workspace(self)
        ws.create()
        state = json.loads((ws.meta / "state.json").read_text("utf-8"))
        state["pluginId"] = "other-plugin"
        (ws.meta / "state.json").write_text(json.dumps(state), "utf-8")
        before = (ws.meta / "state.json").read_bytes()
        code, payload, _ = ws.update("draft_done")
        self.assertEqual(code, 1)
        self.assertIn("other-plugin", payload["errors"][0])
        self.assertEqual((ws.meta / "state.json").read_bytes(), before)

    def test_read_only_commands_do_not_write(self):
        ws = Workspace(self)
        before = sorted(path for path in ws.root.rglob("*"))
        code, payload, _ = ws.host(INSPECT, "--mode", "project", "--workspace", str(ws.root), "--projects", "p1")
        self.assertEqual(code, 0)
        self.assertEqual(payload["projects"]["p1"]["runs"], [])
        self.assertEqual(ws.run()["currentNodeId"], "unknown")
        code, payload, _ = ws.host("runtime/session/render_session_context.py", "--platform", "darwin",
                                   "--plugin-workspace", str(ws.root), "--project", "p1", "--feature", "f1",
                                   "--selected-deployUnit", "not-json")
        self.assertEqual(code, 0)
        self.assertFalse(payload["ok"])
        self.assertEqual(sorted(path for path in ws.root.rglob("*")), before)

    def test_feature_name_must_be_safe(self):
        ws = Workspace(self)
        code, payload, _ = ws.host("runtime/adapters/init_feature.py", "--workspace", str(ws.root), "--project", "p1",
                                   "--feature", "../x")
        self.assertEqual(code, 1)


class SessionContextTest(unittest.TestCase):
    def test_platform_knowledge_selects_library_for_deploy_unit(self):
        ws = Workspace(self, "fullstack")
        unrelated = ws.root / "其他知识库"
        platform = ws.root / "平台 知识库"
        local = ws.plugin / "sys"
        for directory, unit_id, content in (
            (unrelated, "other", "其他发布单元知识"),
            (platform, "unit", "平台发布单元知识"),
            (local, "unit", "插件发布单元知识"),
        ):
            directory.mkdir()
            (directory / "agents.manifest.json").write_text(json.dumps({"systems": [{
                "systemId": "system", "deployUnits": [{"deployUnitId": unit_id, "agentsPath": "unit.md"}],
            }]}), encoding="utf-8")
            (directory / "unit.md").write_text(content, encoding="utf-8")

        for platform_arg, expected in (
            (json.dumps([{"path": str(unrelated)}, {"path": "${unexpanded}"}, {"path": str(platform)}]),
             "平台发布单元知识"),
            (str(platform), "平台发布单元知识"),
            (json.dumps([{"path": str(unrelated)}]), "插件发布单元知识"),
            ("${knowledgePath}", "插件发布单元知识"),
            ("[]", "插件发布单元知识"),
        ):
            with self.subTest(platform_arg=platform_arg):
                code, payload, _ = ws.host(
                    "runtime/session/render_session_context.py", "--plugin-workspace", str(ws.root), "--project", "p1",
                    "--selected-deployUnit", '[{"deployUnitId":"unit"}]',
                    "--knowledge-path", str(local), "--knowledge-path-platform", platform_arg,
                )
                self.assertEqual(code, 0, payload)
                self.assertTrue(payload["ok"], payload)
                self.assertIn(expected, payload["sessionContext"])

    def test_domain_context_is_fallback_for_missing_unit_content(self):
        ws = Workspace(self, "fullstack")
        knowledge = ws.root / "knowledge"
        knowledge.mkdir()
        (knowledge / "agents.manifest.json").write_text(json.dumps({"systems": [{
            "systemId": "system", "agentsPath": "AGENTS.md",
            "deployUnits": [{"deployUnitId": "unit", "agentsPath": "unit.md"}],
        }]}), encoding="utf-8")
        (knowledge / "AGENTS.md").write_text("系统级知识", encoding="utf-8")
        (ws.root / "AGENTS.md").write_text("工作区指令", encoding="utf-8")
        (ws.root / "CONTEXT.md").write_text("旧工作区词汇表", encoding="utf-8")
        ws.meta.mkdir()
        domain_path = ws.meta / "CONTEXT.md"
        domain_path.write_text("领域词汇表内容", encoding="utf-8")
        unit_doc = knowledge / "unit.md"
        for selected, content, expect_domain in (
            ([], "单元级知识", True),
            ([{"deployUnitId": "unit"}], None, True),
            ([{"deployUnitId": "unit"}], " \n", True),
            ([{"deployUnitId": "unit"}, {"deployUnitId": "unknown"}], "单元级知识", False),
        ):
            with self.subTest(selected=selected, content=content):
                if content is None:
                    unit_doc.unlink(missing_ok=True)
                else:
                    unit_doc.write_text(content, encoding="utf-8")
                code, payload, _ = ws.host(
                    "runtime/session/render_session_context.py", "--plugin-workspace", str(ws.root), "--project", "p1",
                    "--session-workspace-path", str(ws.root), "--knowledge-path", str(knowledge),
                    "--selected-deployUnit", json.dumps(selected),
                )
                self.assertEqual(code, 0, payload)
                self.assertTrue(payload["ok"], payload)
                self.assertIn("当前流程", payload["sessionContext"])
                self.assertIn("工作区指令", payload["sessionContext"])
                self.assertEqual("系统级知识" in payload["sessionContext"], bool(selected))
                self.assertEqual("单元级知识" in payload["sessionContext"], not expect_domain)
                self.assertEqual("领域词汇表内容" in payload["sessionContext"], expect_domain)
                self.assertNotIn("旧工作区词汇表", payload["sessionContext"])
                domain_status = [Path(item["path"]).resolve() for item in payload["agentmdLoadStatus"]
                                 if item["deployUnitId"] == "领域词汇表"]
                self.assertEqual(domain_status, [domain_path.resolve()] if expect_domain else [])

    def test_domain_context_uses_custom_project_metadata_directory(self):
        ws = Workspace(self, "fullstack")
        runtime_path = ws.plugin / "runtime/config/runtime.json"
        runtime_config = json.loads(runtime_path.read_text("utf-8"))
        runtime_config["metaRoot"] = ".custom/metadata"
        runtime_path.write_text(json.dumps(runtime_config), encoding="utf-8")
        for project in ("p1", "p2"):
            directory = ws.root / project / ".custom/metadata"
            directory.mkdir(parents=True)
            (directory / "CONTEXT.md").write_text(f"项目 {project} 词汇表", encoding="utf-8")
        for project, other in (("p1", "p2"), ("p2", "p1")):
            with self.subTest(project=project):
                code, payload, _ = ws.host(
                    "runtime/session/render_session_context.py", "--plugin-workspace", str(ws.root),
                    "--project", project, "--session-workspace-path", str(ws.root),
                )
                self.assertEqual(code, 0, payload)
                self.assertTrue(payload["ok"], payload)
                self.assertIn(f"项目 {project} 词汇表", payload["sessionContext"])
                self.assertNotIn(f"项目 {other} 词汇表", payload["sessionContext"])


class ReservedFieldsTest(unittest.TestCase):
    def test_dynamic_stages_and_skip_are_refused(self):
        ws = Workspace(self)
        flow = ws.flow()
        flow["skip"] = {"locked": []}
        ws.set_flow(flow)
        code, payload, _ = ws.host("runtime/adapters/inspect_workflow_templates.py")
        self.assertEqual(code, 1)
        self.assertIn("D59", payload["errors"][0])

    def test_validate_command_runs_on_done(self):
        ws = Workspace(self)
        flow = ws.flow()
        flow["nodes"][0]["validate"] = '${python} -c "import sys; print(\'不合格\'); sys.exit(3)"'
        ws.set_flow(flow)
        ws.create()
        ws.write("DRAFT.md")
        code, payload, _ = ws.update("draft_done")
        self.assertEqual(code, 1)
        self.assertIn("不合格", payload["errors"][0])
        flow["nodes"][0]["validate"] = '${python} -c "import os; assert os.environ[\'NODE_ID\'] == \'draft\'"'
        ws.set_flow(flow)
        code, payload, _ = ws.update("draft_done")
        self.assertEqual(code, 0, payload)
        self.assertTrue(payload["validation"]["passed"])
        events = [json.loads(line)["eventId"] for line in (ws.meta / "hooks.ndjson").read_text("utf-8").splitlines()]
        self.assertEqual(events, ["node-validate", "node-validate", "update-state"])


class BoardEventsTest(unittest.TestCase):
    def serve(self, status=204):
        received = []

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802
                length = int(self.headers["Content-Length"])
                received.append(json.loads(self.rfile.read(length).decode("utf-8")))
                self.send_response(status)
                self.end_headers()

            def log_message(self, *args):
                pass

        server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return f"http://127.0.0.1:{server.server_address[1]}/rpc", received

    def test_events_follow_commits_and_match_feature_status(self):
        endpoint, received = self.serve()
        ws = Workspace(self)
        env = {"AUTOBIZ_BOARD_ENDPOINT": endpoint}
        code, _, _ = ws.host("runtime/adapters/init_workspace.py", "--workspace", str(ws.root), "--project", "p1",
                             env=env)
        self.assertEqual(code, 0)
        ws.create(env=env)
        ws.write("DRAFT.md")
        ws.update("draft_done", env=env)
        ws.update("draft_done", env=env)
        reasons = [message["params"]["reason"] for message in received]
        self.assertEqual(reasons, ["create_project", "create_feature", "update_state"])
        seqs = [message["params"]["seq"] for message in received]
        self.assertEqual(seqs, sorted(seqs))
        self.assertEqual(received[-1]["params"]["run"], ws.run())
        self.assertEqual(received[-1]["method"], "board/changed")

    def test_unreachable_or_invalid_endpoint_does_not_fail(self):
        ws = Workspace(self)
        for endpoint in ("http://127.0.0.1:9/rpc", "https://example.com/rpc"):
            code, payload, stderr = ws.host("runtime/adapters/init_workspace.py", "--workspace", str(ws.root),
                                            "--project", "p1", env={"AUTOBIZ_BOARD_ENDPOINT": endpoint})
            self.assertEqual(code, 0, payload)
            self.assertIn("board-events", stderr)


if __name__ == "__main__":
    unittest.main()
