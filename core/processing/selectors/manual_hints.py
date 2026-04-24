"""Read supervised selector hints from manual golden artifacts."""

from __future__ import annotations

from pathlib import Path
from typing import Any


MANUAL_GOLDEN_HINT_SOURCE = "manual_golden_hint"


def load_manual_selector_hints(repo_root: Path, case_id: str) -> dict[str, Any]:
    hint_path = repo_root / "assets" / "goldens" / case_id / "trigger_selector.manual.txt"
    if not hint_path.exists():
        return {
            "available": False,
            "hint_file": str(hint_path),
            "selectors": [],
        }

    raw_text = hint_path.read_text(encoding="utf-8")
    selectors: list[str] = []
    seen: set[str] = set()
    for part in raw_text.replace("\n", ",").split(","):
        selector = part.strip()
        if not selector:
            continue
        if selector.endswith(" *"):
            selector = selector[:-2].strip()
        if not selector or selector in seen:
            continue
        seen.add(selector)
        selectors.append(selector)

    return {
        "available": True,
        "hint_file": str(hint_path.relative_to(repo_root)),
        "selectors": selectors,
    }
