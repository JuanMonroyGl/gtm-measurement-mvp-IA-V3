"""CLI entrypoint to run a measurement case skeleton pipeline."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from src.generator.generate_gtm_tag import build_tag_template
from src.generator.generate_trigger import build_consolidated_trigger_selector
from src.plan_parser.extract_plan_from_images import parse_measurement_plan
from src.plan_parser.normalize_plan import normalize_case
from src.scraper.fetch_page import fetch_html
from src.scraper.snapshot_dom import build_dom_snapshot
from src.selectors.build_selectors import propose_selectors
from src.selectors.validate_selectors import validate_selector_candidates


def load_metadata(case_dir: Path) -> dict[str, Any]:
    metadata_path = case_dir / "metadata.json"
    with metadata_path.open("r", encoding="utf-8") as f:
        return json.load(f)


def ensure_output_dir(repo_root: Path, case_id: str) -> Path:
    output_dir = repo_root / "outputs" / case_id
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def run_case(repo_root: Path, case_id: str) -> dict[str, Any]:
    case_dir = repo_root / "inputs" / case_id
    images_dir = case_dir / "images"

    metadata = load_metadata(case_dir)
    output_dir = ensure_output_dir(repo_root, case_id)

    parsed_plan = parse_measurement_plan(images_dir)
    measurement_case = normalize_case(metadata=metadata, parsed_plan=parsed_plan)

    target_url = measurement_case.get("target_url")
    fetch_result = fetch_html(target_url=target_url) if target_url else fetch_html(target_url="")
    dom_snapshot = build_dom_snapshot(
        target_url=target_url or "",
        raw_html=fetch_result.html,
    )

    selector_build_result = propose_selectors(
        measurement_case=measurement_case,
        dom_snapshot=dom_snapshot.__dict__,
    )
    selector_validation = validate_selector_candidates(
        measurement_case=measurement_case,
        dom_snapshot=dom_snapshot.__dict__,
    )

    tag_template = build_tag_template(measurement_case)
    trigger_selector = build_consolidated_trigger_selector(measurement_case)

    measurement_case_path = output_dir / "measurement_case.json"
    tag_template_path = output_dir / "tag_template.js"
    trigger_selector_path = output_dir / "trigger_selector.txt"
    report_path = output_dir / "report.md"

    with measurement_case_path.open("w", encoding="utf-8") as f:
        json.dump(measurement_case, f, ensure_ascii=False, indent=2)

    tag_template_path.write_text(tag_template, encoding="utf-8")
    trigger_selector_path.write_text(trigger_selector, encoding="utf-8")

    report_lines = [
        f"# Reporte {case_id}",
        "",
        "## Estado",
        "- Pipeline en modo esqueleto (Fase 1).",
        "- Sin scraping complejo ni generación GTM final.",
        "",
        "## Parser de imágenes",
        f"- parser_status: {parsed_plan.get('parser_status')}",
        f"- image_count: {parsed_plan.get('image_count')}",
        "",
        "## Scraping/DOM",
        f"- fetch_warning: {fetch_result.warning}",
        f"- dom_warning: {dom_snapshot.warning}",
        "",
        "## Selectores",
        f"- build_status: {selector_build_result.get('status')}",
        f"- validation_status: {selector_validation.get('status')}",
        "",
        "## Alertas",
        "- Este resultado NO está listo para producción sin revisión humana.",
    ]
    report_path.write_text("\n".join(report_lines) + "\n", encoding="utf-8")

    return {
        "case_id": case_id,
        "output_dir": str(output_dir),
        "measurement_case": str(measurement_case_path),
        "tag_template": str(tag_template_path),
        "trigger_selector": str(trigger_selector_path),
        "report": str(report_path),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run measurement case pipeline skeleton")
    parser.add_argument("--case-id", required=True, help="Case id, e.g. case_001")
    parser.add_argument(
        "--repo-root",
        default=".",
        help="Repository root containing inputs/ and outputs/",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    result = run_case(repo_root=Path(args.repo_root), case_id=args.case_id)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
