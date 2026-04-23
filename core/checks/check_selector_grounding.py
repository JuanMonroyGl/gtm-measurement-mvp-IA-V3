#!/usr/bin/env python3
"""Regression check: selectors must be grounded in clickable inventory evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate selector grounding against selector_trace/clickable_inventory")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--case-id", required=True)
    args = parser.parse_args()

    root = Path(args.repo_root)
    case_id = args.case_id
    output_dir = root / "outputs" / case_id

    measurement_case_path = output_dir / "measurement_case.json"
    selector_trace_path = output_dir / "selector_trace.json"
    clickable_inventory_path = output_dir / "clickable_inventory.json"

    for path in (measurement_case_path, selector_trace_path, clickable_inventory_path):
        if not path.exists():
            raise SystemExit(f"ERROR: missing required file: {path}")

    measurement_case = json.loads(measurement_case_path.read_text(encoding="utf-8"))
    selector_trace = json.loads(selector_trace_path.read_text(encoding="utf-8"))
    clickable_inventory = json.loads(clickable_inventory_path.read_text(encoding="utf-8"))

    observed_selectors = set()
    for item in clickable_inventory.get("items", []):
        for selector in item.get("selector_candidates") or []:
            observed_selectors.add(str(selector))

    evidence_by_index = {int(item.get("index")): item for item in selector_trace.get("selector_evidence") or [] if item.get("index")}

    for idx, interaction in enumerate(measurement_case.get("interacciones", []), start=1):
        selector = interaction.get("selector_candidato")
        evidence = evidence_by_index.get(idx, {})
        origin = evidence.get("selector_origin")

        if selector is None:
            continue

        if origin != "observed_in_dom":
            raise SystemExit(
                f"ERROR: interaction[{idx}] selector has non-observed origin: selector={selector}, origin={origin}"
            )

        if selector not in observed_selectors:
            raise SystemExit(
                f"ERROR: interaction[{idx}] selector is not present in clickable inventory: {selector}"
            )

    print("OK: selector grounding checks passed")


if __name__ == "__main__":
    main()
