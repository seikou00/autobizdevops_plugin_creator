"""lib/ 的单元测试：推导规则、SKILL.md 片段、Schema 子集、文件读写（scaffold.md 单元 1、2）。"""

import json
import unittest

from tests.helpers import REPO
from scaffold.lib import derive, fsio, jsonschema, skillmd


class DeriveTest(unittest.TestCase):
    def test_artifact_ids_follow_input_config(self):
        cases = {"PRD.md": "prd", "plan.json": "plan_json", "UI_CONTEXT.json": "ui_context_json",
                 "specs/**/*.md": "specs", ".design-contract.lock.json": "design_contract_lock_json",
                 "evidence/EVIDENCE.jsonl": "evidence_jsonl", "specs/*/spec.md": "spec", "*.md": ""}
        for path, expected in cases.items():
            self.assertEqual(derive.artifact_id(path), expected, path)

    def test_artifact_type_and_unsafe_paths(self):
        self.assertEqual(derive.artifact_type("a/b.JSON"), "json")
        self.assertEqual(derive.artifact_type("a.md"), "file")
        for path in ("/abs.md", "../x.md", "a\\b.md", "C:x.md", "state.json"):
            self.assertTrue(derive.unsafe_path(path), path)
        self.assertEqual(derive.unsafe_path("specs/**/*.md"), "")

    def test_ordered_by_seq(self):
        workflow = {"nodes": {"dev": [{"id": "b", "seq": 20}], "biz": [{"id": "a", "seq": 30}, {"id": "c", "seq": 10}]}}
        self.assertEqual([ref.node["id"] for ref in derive.ordered_nodes(workflow)], ["c", "b", "a"])


class SkillMdTest(unittest.TestCase):
    def test_upsert_then_remove_keeps_body(self):
        text = "---\nname: x\ndescription: d\n---\n\n# 标题\n正文\n"
        block = skillmd.render_state_block("plan", False)
        inserted = skillmd.upsert_state(text, block)
        self.assertTrue(inserted.startswith("---\nname: x\ndescription: d\n---\n\n" + block + "\n\n# 标题"))
        self.assertEqual(skillmd.upsert_state(inserted, block), inserted)
        self.assertEqual(skillmd.remove_state(inserted), "---\nname: x\ndescription: d\n---\n\n# 标题\n正文\n")

    def test_crlf_is_preserved_and_digest_is_stable(self):
        text = "---\r\nname: x\r\ndescription: d\r\n---\r\n\r\n正文\r\n"
        block = skillmd.render_state_block("plan", False)
        inserted = skillmd.upsert_state(text, block)
        self.assertNotIn("\n", inserted.replace("\r\n", ""))
        self.assertEqual(skillmd.state_digest(inserted), skillmd.block_digest(block))

    def test_terminal_block_has_only_finish(self):
        block = skillmd.render_state_block("archive", True)
        self.assertIn("--checkpoint archived", block)
        self.assertNotIn("技能开始执行", block)

    def test_frontmatter_limits(self):
        good = skillmd.parse_frontmatter("---\nname: x\ndescription: 'a: b'\nmetadata:\n  version: v1\n---\nbody")
        self.assertEqual(good.fields, {"name": "x", "description": "a: b", "metadata": {"version": "v1"}})
        self.assertEqual(good.errors, [])
        bad = skillmd.parse_frontmatter("---\nname: x\ndescription: >\n  long\n---\n")
        self.assertTrue(bad.errors)

    def test_migrate_version_into_metadata(self):
        text, notes = skillmd.migrate_frontmatter("---\nname: x\nversion: v3\ndescription: d\n---\nbody")
        self.assertEqual(text, "---\nname: x\ndescription: d\nmetadata:\n  version: v3\n---\nbody")
        self.assertEqual(len(notes), 1)

    def test_legacy_state_block_replaced(self):
        text = "---\nname: x\n---\n<!-- scaffold:begin state -->\nold\n<!-- scaffold:end state -->\n正文\n"
        result = skillmd.upsert_state(text, skillmd.render_state_block("a", False))
        self.assertNotIn("scaffold:begin", result)
        self.assertIn(skillmd.STATE_BEGIN, result)


class SchemaTest(unittest.TestCase):
    SCHEMAS = ("plugin-scaffold.schema.json", "workflow.schema.json", "modules/board.schema.json",
               "modules/session.schema.json", "modules/knowledge.schema.json", "modules/artifactSync.schema.json",
               "host/outputs.schema.json")

    def test_schemas_only_use_supported_keywords(self):
        for name in self.SCHEMAS:
            used = jsonschema.keywords_used(jsonschema.load_schema(name))
            self.assertEqual(used - jsonschema.KEYWORDS - jsonschema.ANNOTATIONS, set(), name)

    def test_defaults_only_create_objects_with_default(self):
        schema = jsonschema.load_schema("modules/knowledge.schema.json")
        filled = jsonschema.apply_defaults({}, schema)
        self.assertNotIn("source", filled)
        self.assertEqual(filled["assembly"], {"enabled": True, "assembler": "plugin", "timeoutSec": 30})

    def test_one_of_requires_exactly_one(self):
        schema = jsonschema.load_schema("modules/artifactSync.schema.json")
        both = {"artifacts": {}, "allowedFrom": "a", "allowedCheckpoints": ["a_done"]}
        self.assertTrue(jsonschema.validate(both, schema))
        self.assertEqual(jsonschema.validate({"artifacts": {}, "allowedFrom": "a"}, schema), [])

    def test_examples_pass_schemas(self):
        for example in ("minimal", "lite", "fullstack"):
            base = REPO / "examples" / example
            self.assertEqual(jsonschema.validate(fsio.read_json(base / "workflow.json"),
                                                 jsonschema.load_schema("workflow.schema.json")), [], example)


class FsioTest(unittest.TestCase):
    def test_duplicate_keys_and_bom(self):
        with self.assertRaises(fsio.JsonError):
            fsio.parse_json(b'{"a": 1, "a": 2}')
        self.assertEqual(fsio.parse_json("﻿{\"a\": 1}".encode("utf-8")), {"a": 1})

    def test_digest_ignores_crlf_for_text(self):
        self.assertEqual(fsio.digest(b"a\r\nb\n"), fsio.digest(b"a\nb\n"))
        self.assertNotEqual(fsio.digest(b"\0a\r\n"), fsio.digest(b"\0a\n"))

    def test_dump_json_format(self):
        self.assertEqual(fsio.dump_json({"a": ["中"]}), json.dumps({"a": ["中"]}, ensure_ascii=False, indent=2)
                         .encode("utf-8") + b"\n")


if __name__ == "__main__":
    unittest.main()
