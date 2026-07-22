from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from validate_skill import validate_skill  # noqa: E402


class ValidateSkillTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        (self.root / "references").mkdir()
        (self.root / "evals").mkdir()
        self._write_minimal_valid_skill()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _write_minimal_valid_skill(self) -> None:
        (self.root / "SKILL.md").write_text(
            "---\nname: fixture-skill\ndescription: A fixture skill for validator tests.\n---\n"
            "# Fixture\nUse [topic](references/topic.md).\n",
            encoding="utf-8",
        )
        (self.root / "references" / "canonical-contract.md").write_text(
            "# Contract\n\n**Contract version:** `1.0.0`\n\n### TERM-TEST — Test term\n\n### INV-TEST-001 — Test invariant\n",
            encoding="utf-8",
        )
        (self.root / "references" / "topic.md").write_text("# Topic\n", encoding="utf-8")
        self._write_routes(
            {
                "schema_version": "1.0.0",
                "defaults": {
                    "canonical_contract": "references/canonical-contract.md",
                    "contract_version": "1.0.0",
                    "max_primary": 1,
                    "max_supplements": 2,
                    "selection_order": [
                        "exclude_negative_matches",
                        "exact_intent_matches",
                        "positive_signal_matches",
                        "priority",
                        "longest_signal",
                        "route_id",
                    ],
                    "expand_only_for": ["cross_module_design"],
                    "coverage_exempt": ["references/canonical-contract.md"],
                    "scope": "single_agent_or_limited_runtime",
                    "handoff": {
                        "target_skill": "agent-platform-engineering-skill",
                        "exact_intents": ["build_agent_platform"],
                        "positive_signals": ["多租户"],
                        "retain_core_foundation_routes": ["fixture.topic"],
                    },
                },
                "routes": [self._valid_route()],
            }
        )
        self._write_evals(self._valid_evals())

    @staticmethod
    def _valid_route() -> dict:
        return {
            "id": "fixture.topic",
            "intents": ["test_fixture"],
            "positive_signals": ["fixture"],
            "negative_signals": [],
            "primary": "references/topic.md",
            "supplements": [],
            "contract_ids": ["TERM-TEST", "INV-TEST-001"],
            "priority": 1,
        }

    @staticmethod
    def _valid_evals() -> dict:
        return {
            "schema_version": "1.0.0",
            "skill_name": "fixture-skill",
            "evals": [
                {
                    "id": 1,
                    "prompt": "Review a dangerous agent.",
                    "expected_output": "A safe review.",
                    "tags": ["security"],
                    "risk": "high",
                    "files": [],
                    "routing_expectation": {
                        "route_id": "fixture.topic",
                        "primary": "references/topic.md",
                        "required_contract_ids": ["TERM-TEST", "INV-TEST-001"],
                        "max_loaded_references": 1,
                    },
                    "assertions": [
                        {
                            "text": "Requires explicit approval.",
                            "type": "output_semantic",
                            "severity": "hard",
                            "negative": False,
                        },
                        {
                            "text": "Does not recommend unrestricted execution.",
                            "type": "output_not_semantic",
                            "severity": "hard",
                            "negative": True,
                        },
                    ],
                }
            ],
        }

    def _write_routes(self, data: dict) -> None:
        (self.root / "references" / "routes.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    def _read_routes(self) -> dict:
        return json.loads((self.root / "references" / "routes.json").read_text(encoding="utf-8"))

    def _write_evals(self, data: dict) -> None:
        (self.root / "evals" / "evals.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    def _categories(self) -> set[str]:
        return {issue.category for issue in validate_skill(self.root)}

    def test_valid_fixture_passes(self) -> None:
        self.assertEqual([], validate_skill(self.root))

    def test_missing_route_target_fails(self) -> None:
        routes = self._read_routes()
        routes["routes"][0]["primary"] = "references/missing.md"
        self._write_routes(routes)
        self.assertIn("ROUTE_TARGET", self._categories())

    def test_duplicate_route_id_fails(self) -> None:
        routes = self._read_routes()
        routes["routes"].append(dict(routes["routes"][0]))
        self._write_routes(routes)
        self.assertIn("ROUTE", self._categories())

    def test_orphan_reference_fails(self) -> None:
        (self.root / "references" / "orphan.md").write_text("# Orphan\n", encoding="utf-8")
        self.assertIn("ORPHAN_REFERENCE", self._categories())

    def test_unknown_contract_id_fails(self) -> None:
        routes = self._read_routes()
        routes["routes"][0]["contract_ids"].append("INV-UNKNOWN-999")
        self._write_routes(routes)
        self.assertIn("CONTRACT_REF", self._categories())

    def test_broken_markdown_link_fails(self) -> None:
        (self.root / "references" / "topic.md").write_text(
            "# Topic\n[missing](missing.md)\n", encoding="utf-8"
        )
        self.assertIn("LINK", self._categories())

    def test_eval_without_assertions_fails(self) -> None:
        evals = self._valid_evals()
        evals["evals"][0]["assertions"] = []
        self._write_evals(evals)
        self.assertIn("EVAL_ASSERTION", self._categories())

    def test_high_risk_eval_without_hard_assertion_fails(self) -> None:
        evals = self._valid_evals()
        for assertion in evals["evals"][0]["assertions"]:
            assertion["severity"] = "soft"
        self._write_evals(evals)
        self.assertIn("EVAL_RISK", self._categories())

    def test_high_risk_eval_without_negative_assertion_fails(self) -> None:
        evals = self._valid_evals()
        for assertion in evals["evals"][0]["assertions"]:
            assertion["negative"] = False
        self._write_evals(evals)
        self.assertIn("EVAL_RISK", self._categories())

    def test_missing_route_priority_fails(self) -> None:
        routes = self._read_routes()
        del routes["routes"][0]["priority"]
        self._write_routes(routes)
        self.assertIn("ROUTE", self._categories())

    def test_missing_stable_selection_order_fails(self) -> None:
        routes = self._read_routes()
        routes["defaults"]["selection_order"] = ["priority"]
        self._write_routes(routes)
        self.assertIn("ROUTE", self._categories())

    def test_contract_version_mismatch_fails(self) -> None:
        routes = self._read_routes()
        routes["defaults"]["contract_version"] = "2.0.0"
        self._write_routes(routes)
        self.assertIn("CONTRACT", self._categories())

    def test_reference_used_only_as_supplement_fails(self) -> None:
        extra = self.root / "references" / "extra.md"
        extra.write_text("# Extra\n", encoding="utf-8")
        routes = self._read_routes()
        routes["routes"][0]["supplements"] = ["references/extra.md"]
        self._write_routes(routes)
        self.assertIn("PRIMARY_COVERAGE", self._categories())

    def test_eval_with_unknown_assertion_type_fails(self) -> None:
        evals = self._valid_evals()
        evals["evals"][0]["assertions"][0]["type"] = "semanticish"
        self._write_evals(evals)
        self.assertIn("EVAL_ASSERTION", self._categories())

    def test_eval_without_routing_expectation_fails(self) -> None:
        evals = self._valid_evals()
        del evals["evals"][0]["routing_expectation"]
        self._write_evals(evals)
        self.assertIn("EVAL_ROUTE", self._categories())

    def test_eval_with_route_primary_mismatch_fails(self) -> None:
        evals = self._valid_evals()
        evals["evals"][0]["routing_expectation"]["primary"] = "references/wrong.md"
        self._write_evals(evals)
        self.assertIn("EVAL_ROUTE", self._categories())

    def test_high_risk_eval_with_only_soft_negative_fails(self) -> None:
        evals = self._valid_evals()
        evals["evals"][0]["assertions"][1]["severity"] = "soft"
        self._write_evals(evals)
        self.assertIn("EVAL_RISK", self._categories())

    def test_existing_file_in_future_roadmap_fails(self) -> None:
        topic = self.root / "references" / "topic.md"
        topic.write_text(
            "# Topic\n\n## 后续可继续拆分\n\n- `topic.md`\n", encoding="utf-8"
        )
        self.assertIn("ROADMAP_STALE", self._categories())

    def test_missing_handoff_defaults_fails(self) -> None:
        routes = self._read_routes()
        del routes["defaults"]["handoff"]
        self._write_routes(routes)
        self.assertIn("HANDOFF", self._categories())

    def test_route_claiming_handoff_intent_fails(self) -> None:
        routes = self._read_routes()
        routes["routes"][0]["intents"].append("build_agent_platform")
        self._write_routes(routes)
        self.assertIn("HANDOFF", self._categories())

    def test_handoff_eval_target_mismatch_fails(self) -> None:
        evals = self._valid_evals()
        evals["evals"][0]["routing_expectation"] = {
            "mode": "handoff",
            "target_skill": "wrong-skill",
            "max_loaded_references": 0,
        }
        self._write_evals(evals)
        self.assertIn("EVAL_ROUTE", self._categories())

    def test_handoff_eval_with_core_primary_fails(self) -> None:
        evals = self._valid_evals()
        evals["evals"][0]["routing_expectation"] = {
            "mode": "handoff",
            "target_skill": "agent-platform-engineering-skill",
            "primary": "references/topic.md",
            "max_loaded_references": 0,
        }
        self._write_evals(evals)
        self.assertIn("EVAL_ROUTE", self._categories())


if __name__ == "__main__":
    unittest.main()
