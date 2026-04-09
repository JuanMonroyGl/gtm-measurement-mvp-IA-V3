"""Normalization utilities for measurement cases."""

from __future__ import annotations

from typing import Any


INTERACTION_FIELDS = [
    "tipo_evento",
    "activo",
    "seccion",
    "flujo",
    "elemento",
    "ubicacion",
    "plan_url",
    "target_url",
    "page_path_regex",
    "texto_referencia",
    "selector_candidato",
    "selector_activador",
    "match_count",
    "confidence",
    "warnings",
]


def normalize_case(metadata: dict[str, Any], parsed_plan: dict[str, Any]) -> dict[str, Any]:
    """Create normalized case skeleton from metadata + parsed plan result."""
    base = {
        "case_id": metadata.get("case_id"),
        "activo": metadata.get("activo"),
        "seccion": metadata.get("seccion"),
        "plan_url": metadata.get("plan_url"),
        "target_url": metadata.get("target_url"),
        "page_path_regex": metadata.get("page_path_regex"),
        "notes": metadata.get("notes"),
        "interacciones": [],
    }

    # Placeholder for future mapping from parsed_plan["interactions_raw"]
    # while preserving nulls for non-inferable fields.
    _ = parsed_plan
    return base
