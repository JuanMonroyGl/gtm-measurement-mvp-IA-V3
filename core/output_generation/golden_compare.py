"""Textual comparison between generated GTM artifacts and manual goldens."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from core.output_generation.generate_gtm_tag import FORBIDDEN_ABSTRACT_HELPERS


def _branch_count(tag_text: str) -> int:
    return len(re.findall(r"\b(?:if|else\s+if)\s*\(\s*e\.closest\(", tag_text))


def _track_events(tag_text: str) -> list[str]:
    return re.findall(r"analytics\.track\(\s*['\"]([^'\"]+)['\"]", tag_text)


def _trigger_selectors(trigger_text: str) -> list[str]:
    return [part.strip() for part in trigger_text.split(",") if part.strip()]


def compare_with_manual_golden(
    *,
    repo_root: Path,
    case_id: str,
    generated_tag: str,
    generated_trigger: str,
) -> dict[str, Any]:
    golden_dir = repo_root / "assets" / "goldens" / case_id
    manual_tag_path = golden_dir / "tag_template.manual.js"
    manual_trigger_path = golden_dir / "trigger_selector.manual.txt"
    if not manual_tag_path.exists() or not manual_trigger_path.exists():
        return {
            "available": False,
            "case_id": case_id,
            "tag_path": str(manual_tag_path),
            "trigger_path": str(manual_trigger_path),
        }

    manual_tag = manual_tag_path.read_text(encoding="utf-8")
    manual_trigger = manual_trigger_path.read_text(encoding="utf-8")
    manual_selectors = _trigger_selectors(manual_trigger)
    generated_selectors = _trigger_selectors(generated_trigger)
    generated_forbidden_helpers = [helper for helper in FORBIDDEN_ABSTRACT_HELPERS if helper in generated_tag]

    return {
        "available": True,
        "case_id": case_id,
        "tag_path": str(manual_tag_path),
        "trigger_path": str(manual_trigger_path),
        "manual_branch_count": _branch_count(manual_tag),
        "generated_branch_count": _branch_count(generated_tag),
        "manual_events": _track_events(manual_tag),
        "generated_events": _track_events(generated_tag),
        "manual_selector_count": len(manual_selectors),
        "generated_selector_count": len(generated_selectors),
        "manual_selectors": manual_selectors,
        "generated_selectors": generated_selectors,
        "generated_forbidden_helpers": generated_forbidden_helpers,
        "generated_uses_json_rule_blob": "var groupRule = {" in generated_tag or '"element_variants":' in generated_tag,
        "generated_uses_abstract_group_logic": bool(generated_forbidden_helpers),
    }
