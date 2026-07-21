#!/usr/bin/env python3
"""Validate the agent-creator skill's routes, contracts, links, and evals."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import unquote


CONTRACT_ID_PATTERN = re.compile(r"^###\s+((?:TERM|INV)-[A-Z0-9-]+)\b", re.MULTILINE)
CONTRACT_VERSION_PATTERN = re.compile(r"^\*\*Contract version:\*\*\s+`([^`]+)`\s*$", re.MULTILINE)
SEMVER_PATTERN = re.compile(r"^\d+\.\d+\.\d+$")
MARKDOWN_LINK_PATTERN = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
ENGINEERING_LINK_PATTERN = re.compile(r"references/engineering/[^)\s]+\.md")
ROADMAP_HEADING_PATTERN = re.compile(r"^#{1,6}\s+.*(?:后续|未来|Roadmap).*(?:增加|新增|拆分|规划)?.*$", re.IGNORECASE)
BACKTICK_MD_PATTERN = re.compile(r"`([^`]+\.md)`")
REQUIRED_ASSERTION_FIELDS = {"text", "type", "severity", "negative"}
REQUIRED_SELECTION_ORDER = [
    "exclude_negative_matches",
    "exact_intent_matches",
    "positive_signal_matches",
    "priority",
    "longest_signal",
    "route_id",
]
VALID_ASSERTION_TYPES = {"output_semantic", "output_contains", "output_not_semantic", "output_not_contains"}
VALID_SEVERITIES = {"soft", "hard"}
VALID_RISKS = {"low", "medium", "high", "critical"}
HIGH_RISKS = {"high", "critical"}


@dataclass(frozen=True)
class Issue:
    category: str
    message: str


def _read_json(path: Path, issues: list[Issue], category: str) -> Any | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        issues.append(Issue(category, f"missing file: {path}"))
    except json.JSONDecodeError as exc:
        issues.append(Issue(category, f"invalid JSON in {path}: {exc}"))
    return None


def _as_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item.strip()]


def _validate_skill_frontmatter(root: Path, issues: list[Issue]) -> None:
    skill_path = root / "SKILL.md"
    try:
        content = skill_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        issues.append(Issue("SKILL", "missing SKILL.md"))
        return

    lines = content.splitlines()
    if not lines or lines[0].strip() != "---":
        issues.append(Issue("SKILL", "SKILL.md must start with YAML frontmatter"))
        return

    try:
        closing = lines.index("---", 1)
    except ValueError:
        issues.append(Issue("SKILL", "SKILL.md frontmatter is not closed"))
        return

    frontmatter = "\n".join(lines[1:closing])
    for field in ("name", "description"):
        if not re.search(rf"^{field}:\s*\S.+$", frontmatter, re.MULTILINE):
            issues.append(Issue("SKILL", f"SKILL.md frontmatter is missing {field}"))

    engineering_links = set(ENGINEERING_LINK_PATTERN.findall(content))
    if len(engineering_links) > 8:
        issues.append(
            Issue(
                "PROGRESSIVE_DISCLOSURE",
                f"SKILL.md duplicates {len(engineering_links)} engineering routes; use references/routes.json",
            )
        )


def _contract_metadata(contract_path: Path, issues: list[Issue]) -> tuple[set[str], str | None]:
    try:
        content = contract_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        issues.append(Issue("CONTRACT", f"missing canonical contract: {contract_path}"))
        return set(), None

    version_match = CONTRACT_VERSION_PATTERN.search(content)
    contract_version = version_match.group(1) if version_match else None
    if contract_version is None or not SEMVER_PATTERN.fullmatch(contract_version):
        issues.append(Issue("CONTRACT", "canonical contract must declare a semantic Contract version"))

    ids = CONTRACT_ID_PATTERN.findall(content)
    seen: set[str] = set()
    for contract_id in ids:
        if contract_id in seen:
            issues.append(Issue("CONTRACT", f"duplicate contract ID: {contract_id}"))
        seen.add(contract_id)
    if not seen:
        issues.append(Issue("CONTRACT", "canonical contract defines no TERM-* or INV-* IDs"))
    return seen, contract_version


def _validate_routes(root: Path, issues: list[Issue]) -> tuple[dict[str, Any] | None, set[str]]:
    routes_path = root / "references" / "routes.json"
    data = _read_json(routes_path, issues, "ROUTE")
    if not isinstance(data, dict):
        return None, set()

    schema_version = data.get("schema_version")
    if not isinstance(schema_version, str) or not SEMVER_PATTERN.fullmatch(schema_version):
        issues.append(Issue("ROUTE", "routes.json schema_version must be semantic version text"))

    defaults = data.get("defaults")
    routes = data.get("routes")
    if not isinstance(defaults, dict):
        issues.append(Issue("ROUTE", "routes.json defaults must be an object"))
        defaults = {}
    if not isinstance(routes, list) or not routes:
        issues.append(Issue("ROUTE", "routes.json routes must be a non-empty array"))
        return data, set()

    max_primary = defaults.get("max_primary")
    if max_primary != 1:
        issues.append(Issue("ROUTE", "defaults.max_primary must be 1"))
    selection_order = defaults.get("selection_order")
    if selection_order != REQUIRED_SELECTION_ORDER:
        issues.append(Issue("ROUTE", "defaults.selection_order must define the stable routing tie-break"))
    expand_only_for = _as_string_list(defaults.get("expand_only_for"))
    if not expand_only_for:
        issues.append(Issue("ROUTE", "defaults.expand_only_for must declare bounded expansion reasons"))

    contract_ref = defaults.get("canonical_contract", "references/canonical-contract.md")
    contract_path = root / str(contract_ref)
    known_contract_ids, contract_version = _contract_metadata(contract_path, issues)
    declared_contract_version = defaults.get("contract_version")
    if declared_contract_version != contract_version:
        issues.append(
            Issue(
                "CONTRACT",
                f"routes.json contract_version {declared_contract_version!r} does not match canonical contract {contract_version!r}",
            )
        )

    route_ids: set[str] = set()
    reachable: set[str] = set()
    primary_targets: set[str] = set()
    max_supplements = defaults.get("max_supplements", 2)
    if not isinstance(max_supplements, int) or max_supplements < 0:
        issues.append(Issue("ROUTE", "defaults.max_supplements must be a non-negative integer"))
        max_supplements = 2

    for index, route in enumerate(routes):
        label = f"route[{index}]"
        if not isinstance(route, dict):
            issues.append(Issue("ROUTE", f"{label} must be an object"))
            continue

        route_id = route.get("id")
        if not isinstance(route_id, str) or not route_id.strip():
            issues.append(Issue("ROUTE", f"{label} has no valid id"))
            route_id = label
        elif route_id in route_ids:
            issues.append(Issue("ROUTE", f"duplicate route ID: {route_id}"))
        else:
            route_ids.add(route_id)
        label = str(route_id)

        if not _as_string_list(route.get("intents")):
            issues.append(Issue("ROUTE", f"{label} has no intents"))
        if not _as_string_list(route.get("positive_signals")):
            issues.append(Issue("ROUTE", f"{label} has no positive_signals"))
        if not isinstance(route.get("negative_signals"), list):
            issues.append(Issue("ROUTE", f"{label} negative_signals must be an array"))

        priority = route.get("priority")
        if not isinstance(priority, int) or isinstance(priority, bool) or not 0 <= priority <= 100:
            issues.append(Issue("ROUTE", f"{label} priority must be an integer from 0 to 100"))

        primary = route.get("primary")
        supplements = _as_string_list(route.get("supplements"))
        if not isinstance(primary, str) or not primary.strip():
            issues.append(Issue("ROUTE", f"{label} has no primary document"))
            primary = ""
        if len(supplements) > max_supplements:
            issues.append(
                Issue("ROUTE", f"{label} has {len(supplements)} supplements; maximum is {max_supplements}")
            )
        if primary and primary in supplements:
            issues.append(Issue("ROUTE", f"{label} includes its primary as a supplement"))
        if len(supplements) != len(set(supplements)):
            issues.append(Issue("ROUTE", f"{label} has duplicate supplements"))

        if primary:
            primary_targets.add(Path(primary).as_posix())
        for target in [primary, *supplements]:
            if not target:
                continue
            target_path = root / target
            if not target_path.is_file():
                issues.append(Issue("ROUTE_TARGET", f"{label} references missing file: {target}"))
            reachable.add(Path(target).as_posix())

        contract_ids = _as_string_list(route.get("contract_ids"))
        if not contract_ids:
            issues.append(Issue("ROUTE", f"{label} has no contract_ids"))
        for contract_id in contract_ids:
            if contract_id not in known_contract_ids:
                issues.append(Issue("CONTRACT_REF", f"{label} references unknown contract ID: {contract_id}"))

    exempt = {Path(item).as_posix() for item in _as_string_list(defaults.get("coverage_exempt"))}
    all_references = {
        path.relative_to(root).as_posix()
        for path in (root / "references").rglob("*.md")
        if path.is_file()
    }
    orphaned = sorted(all_references - reachable - exempt)
    for reference in orphaned:
        issues.append(Issue("ORPHAN_REFERENCE", f"reference is unreachable from routes.json: {reference}"))
    supplement_only = sorted(all_references - primary_targets - exempt)
    for reference in supplement_only:
        issues.append(Issue("PRIMARY_COVERAGE", f"reference has no direct primary route: {reference}"))

    return data, known_contract_ids


def _clean_link_target(raw_target: str) -> str:
    target = raw_target.strip()
    if target.startswith("<") and target.endswith(">"):
        target = target[1:-1].strip()
    target = target.split(maxsplit=1)[0]
    target = unquote(target.split("#", 1)[0])
    return target


def _validate_markdown_links(root: Path, issues: list[Issue]) -> None:
    markdown_files = [root / "SKILL.md", *(root / "references").rglob("*.md")]
    for markdown_path in markdown_files:
        if not markdown_path.is_file():
            continue
        content = markdown_path.read_text(encoding="utf-8")
        for raw_target in MARKDOWN_LINK_PATTERN.findall(content):
            target = _clean_link_target(raw_target)
            if not target or re.match(r"^[a-z][a-z0-9+.-]*:", target, re.IGNORECASE):
                continue
            resolved = (markdown_path.parent / target).resolve()
            if not resolved.exists():
                relative_source = markdown_path.relative_to(root).as_posix()
                issues.append(Issue("LINK", f"{relative_source} -> {target} does not exist"))


def _validate_evals(
    root: Path,
    issues: list[Issue],
    route_data: dict[str, Any] | None,
    known_contract_ids: set[str],
) -> None:
    evals_path = root / "evals" / "evals.json"
    data = _read_json(evals_path, issues, "EVAL")
    if not isinstance(data, dict):
        return
    schema_version = data.get("schema_version")
    if not isinstance(schema_version, str) or not SEMVER_PATTERN.fullmatch(schema_version):
        issues.append(Issue("EVAL", "evals.json schema_version must be semantic version text"))
    evals = data.get("evals")
    if not isinstance(evals, list) or not evals:
        issues.append(Issue("EVAL", "evals.json evals must be a non-empty array"))
        return

    route_map: dict[str, dict[str, Any]] = {}
    max_loaded_references = 3
    if isinstance(route_data, dict):
        route_map = {
            route["id"]: route
            for route in route_data.get("routes", [])
            if isinstance(route, dict) and isinstance(route.get("id"), str)
        }
        defaults = route_data.get("defaults", {})
        if isinstance(defaults, dict):
            max_loaded_references = int(defaults.get("max_primary", 1)) + int(
                defaults.get("max_supplements", 2)
            )

    seen_ids: set[Any] = set()
    for index, case in enumerate(evals):
        label = f"eval[{index}]"
        if not isinstance(case, dict):
            issues.append(Issue("EVAL", f"{label} must be an object"))
            continue
        eval_id = case.get("id")
        if isinstance(eval_id, bool) or not isinstance(eval_id, (int, str)) or not str(eval_id).strip():
            issues.append(Issue("EVAL", f"{label} has no valid id"))
        elif eval_id in seen_ids:
            issues.append(Issue("EVAL", f"duplicate eval ID: {eval_id}"))
        seen_ids.add(eval_id)
        label = f"eval {eval_id}"

        for field in ("prompt", "expected_output"):
            if not isinstance(case.get(field), str) or not case[field].strip():
                issues.append(Issue("EVAL", f"{label} {field} must be non-empty text"))
        risk = case.get("risk")
        if risk not in VALID_RISKS:
            issues.append(Issue("EVAL", f"{label} has invalid risk: {risk}"))
        tags = case.get("tags")
        if not _as_string_list(tags) or len(_as_string_list(tags)) != len(tags) if isinstance(tags, list) else True:
            issues.append(Issue("EVAL", f"{label} tags must be a non-empty string array"))

        routing = case.get("routing_expectation")
        if not isinstance(routing, dict):
            issues.append(Issue("EVAL_ROUTE", f"{label} must declare routing_expectation"))
        else:
            route_id = routing.get("route_id")
            route = route_map.get(route_id) if isinstance(route_id, str) else None
            if route is None:
                issues.append(Issue("EVAL_ROUTE", f"{label} references unknown route: {route_id}"))
            else:
                if routing.get("primary") != route.get("primary"):
                    issues.append(Issue("EVAL_ROUTE", f"{label} primary does not match route {route_id}"))
                required_contract_ids = _as_string_list(routing.get("required_contract_ids"))
                if not required_contract_ids:
                    issues.append(Issue("EVAL_ROUTE", f"{label} has no required_contract_ids"))
                route_contract_ids = set(_as_string_list(route.get("contract_ids")))
                for contract_id in required_contract_ids:
                    if contract_id not in known_contract_ids or contract_id not in route_contract_ids:
                        issues.append(
                            Issue(
                                "EVAL_ROUTE",
                                f"{label} expects contract {contract_id} not supplied by route {route_id}",
                            )
                        )
                loaded = routing.get("max_loaded_references")
                if not isinstance(loaded, int) or isinstance(loaded, bool) or not 1 <= loaded <= max_loaded_references:
                    issues.append(
                        Issue(
                            "EVAL_ROUTE",
                            f"{label} max_loaded_references must be from 1 to {max_loaded_references}",
                        )
                    )

        assertions = case.get("assertions")
        if not isinstance(assertions, list) or not assertions:
            issues.append(Issue("EVAL_ASSERTION", f"{label} has expected_output but no assertions"))
            continue

        has_hard = False
        has_hard_negative = False
        for assertion_index, assertion in enumerate(assertions):
            assertion_label = f"{label} assertion[{assertion_index}]"
            if not isinstance(assertion, dict):
                issues.append(Issue("EVAL_ASSERTION", f"{assertion_label} must be an object"))
                continue
            missing = REQUIRED_ASSERTION_FIELDS - assertion.keys()
            if missing:
                issues.append(
                    Issue("EVAL_ASSERTION", f"{assertion_label} is missing: {', '.join(sorted(missing))}")
                )
            text = assertion.get("text")
            if not isinstance(text, str) or not text.strip():
                issues.append(Issue("EVAL_ASSERTION", f"{assertion_label} text must be non-empty"))
            assertion_type = assertion.get("type")
            if assertion_type not in VALID_ASSERTION_TYPES:
                issues.append(Issue("EVAL_ASSERTION", f"{assertion_label} has invalid type: {assertion_type}"))
            severity = assertion.get("severity")
            if severity not in VALID_SEVERITIES:
                issues.append(Issue("EVAL_ASSERTION", f"{assertion_label} has invalid severity: {severity}"))
            if severity == "hard":
                has_hard = True
            negative = assertion.get("negative")
            if not isinstance(negative, bool):
                issues.append(Issue("EVAL_ASSERTION", f"{assertion_label} negative must be boolean"))
            else:
                type_is_negative = isinstance(assertion_type, str) and assertion_type.startswith("output_not_")
                if negative != type_is_negative:
                    issues.append(
                        Issue("EVAL_ASSERTION", f"{assertion_label} type and negative flag disagree")
                    )
                if negative and severity == "hard":
                    has_hard_negative = True

        if risk in HIGH_RISKS:
            if not has_hard:
                issues.append(Issue("EVAL_RISK", f"{label} is high risk but has no hard assertion"))
            if not has_hard_negative:
                issues.append(Issue("EVAL_RISK", f"{label} is high risk but has no hard negative assertion"))


def _roadmap_sections(content: str) -> Iterable[tuple[int, list[str]]]:
    lines = content.splitlines()
    index = 0
    while index < len(lines):
        if not ROADMAP_HEADING_PATTERN.match(lines[index]):
            index += 1
            continue
        start = index
        index += 1
        section: list[str] = []
        while index < len(lines) and not re.match(r"^#{1,6}\s+", lines[index]):
            section.append(lines[index])
            index += 1
        yield start + 1, section


def _validate_roadmaps(root: Path, issues: list[Issue]) -> None:
    markdown_files = [root / "SKILL.md", *(root / "references").rglob("*.md")]
    for markdown_path in markdown_files:
        if not markdown_path.is_file():
            continue
        content = markdown_path.read_text(encoding="utf-8")
        for line_number, section in _roadmap_sections(content):
            for candidate in BACKTICK_MD_PATTERN.findall("\n".join(section)):
                possible_paths = [markdown_path.parent / candidate, root / "references" / "engineering" / candidate]
                if any(path.is_file() for path in possible_paths):
                    source = markdown_path.relative_to(root).as_posix()
                    issues.append(
                        Issue(
                            "ROADMAP_STALE",
                            f"{source}:{line_number} lists existing file as future work: {candidate}",
                        )
                    )


def validate_skill(root: Path) -> list[Issue]:
    root = root.resolve()
    issues: list[Issue] = []
    _validate_skill_frontmatter(root, issues)
    route_data, known_contract_ids = _validate_routes(root, issues)
    _validate_markdown_links(root, issues)
    _validate_evals(root, issues, route_data, known_contract_ids)
    _validate_roadmaps(root, issues)
    return issues


def format_issues(issues: Iterable[Issue]) -> str:
    grouped: dict[str, list[str]] = defaultdict(list)
    for issue in issues:
        grouped[issue.category].append(issue.message)
    lines: list[str] = []
    for category in sorted(grouped):
        lines.append(f"[{category}]")
        lines.extend(f"- {message}" for message in grouped[category])
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", default=".", help="skill root directory")
    args = parser.parse_args(argv)
    root = Path(args.root)
    issues = validate_skill(root)
    if issues:
        print(format_issues(issues))
        print(f"\nValidation failed with {len(issues)} issue(s).")
        return 1
    print("Skill control-plane validation passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
