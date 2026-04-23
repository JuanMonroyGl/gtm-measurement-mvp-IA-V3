"""Validate selector candidates against DOM snapshot and observed inventory."""

from __future__ import annotations

from typing import Any

from bs4 import BeautifulSoup


def validate_selector_candidates(
    measurement_case: dict[str, Any],
    dom_snapshot: dict[str, Any],
    selector_evidence: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    state_html = dom_snapshot.get("state_html") or {}
    if not state_html:
        return {
            "status": "no_dom",
            "validated_interactions": 0,
            "warnings": ["No hay DOM disponible para validar selectores."],
        }

    selector_origin_by_index = {
        int(item.get("index")): str(item.get("selector_origin"))
        for item in (selector_evidence or [])
        if item.get("index")
    }

    validated = 0
    warnings: list[str] = []

    # validate against best state count
    soups = {state: BeautifulSoup(html, "lxml") for state, html in state_html.items()}

    for idx, interaction in enumerate(measurement_case.get("interacciones", []), start=1):
        selector = interaction.get("selector_candidato")
        interaction.setdefault("warnings", [])

        if selector_origin_by_index.get(idx) != "observed_in_dom":
            interaction["selector_candidato"] = None
            interaction["selector_activador"] = None
            interaction["match_count"] = None
            interaction["warnings"].append(
                "Selector rechazado por no estar observado en DOM renderizado; human_review_required=true."
            )
            continue

        if not selector:
            interaction["match_count"] = None
            interaction["warnings"].append("Sin selector_candidato observado; no se valida match_count.")
            continue

        match_count = 0
        for soup in soups.values():
            try:
                match_count = max(match_count, len(soup.select(selector)))
            except Exception as exc:
                warnings.append(f"Selector inválido detectado: {selector} ({exc})")

        interaction["match_count"] = match_count if match_count > 0 else None
        validated += 1

        if match_count == 0:
            interaction["selector_candidato"] = None
            interaction["selector_activador"] = None
            interaction["match_count"] = None
            interaction["warnings"].append(
                "Selector no encontró matches en estados renderizados; se deja null y human_review_required=true."
            )
        elif match_count > 1:
            interaction["warnings"].append(
                f"Selector observado pero ambiguo ({match_count} matches); se requiere revisión humana."
            )

    return {
        "status": "ok",
        "validated_interactions": validated,
        "warnings": warnings,
    }
