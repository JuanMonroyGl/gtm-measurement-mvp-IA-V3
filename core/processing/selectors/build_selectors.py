"""Selector proposal logic grounded strictly on observed clickable inventory."""

from __future__ import annotations

import re
from typing import Any

from bs4 import BeautifulSoup


def _normalize(text: str | None) -> str:
    if not text:
        return ""
    cleaned = text.lower().strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    replacements = {"á": "a", "é": "e", "í": "i", "ó": "o", "ú": "u", "¿": "", "?": ""}
    for src, dst in replacements.items():
        cleaned = cleaned.replace(src, dst)
    return cleaned


def _tokenize(value: str | None) -> list[str]:
    normalized = _normalize(value)
    if not normalized:
        return []
    stopwords = {"de", "la", "el", "los", "las", "y", "en", "del", "para", "con", "por", "un", "una", "al"}
    return [t for t in re.split(r"[^a-z0-9]+", normalized) if len(t) >= 3 and t not in stopwords]


def _interaction_tokens(interaction: dict[str, Any]) -> list[str]:
    tokens: list[str] = []
    for field in ("texto_referencia", "elemento", "ubicacion", "flujo", "tipo_evento"):
        tokens.extend(_tokenize(interaction.get(field)))
    return list(dict.fromkeys(tokens))


def _selector_match_count(selector: str, state_html: dict[str, str]) -> tuple[int, str | None]:
    best_count = 0
    best_state: str | None = None
    for state, html in state_html.items():
        try:
            soup = BeautifulSoup(html, "lxml")
            count = len(soup.select(selector))
        except Exception:
            count = 0
        if count > best_count:
            best_count = count
            best_state = state
    return best_count, best_state


def _closest_compatible(selector: str, item: dict[str, Any], state_html: dict[str, str], state: str | None) -> bool:
    state_to_use = state or next(iter(state_html.keys()), None)
    if not state_to_use:
        return False
    html = state_html.get(state_to_use)
    if not html:
        return False
    try:
        soup = BeautifulSoup(html, "lxml")
        direct_matches = soup.select(selector)
        if not direct_matches:
            return False
        excerpt = _normalize(item.get("outer_html_excerpt"))
        return bool(excerpt)
    except Exception:
        return False


def _candidate_evidence(
    *,
    interaction: dict[str, Any],
    item: dict[str, Any],
    selector: str,
    state_html: dict[str, str],
) -> dict[str, Any]:
    tokens = _interaction_tokens(interaction)
    haystack = _normalize(" ".join([
        str(item.get("text") or ""),
        str(item.get("aria_label") or ""),
        str(item.get("title") or ""),
        str(item.get("href") or ""),
    ]))
    matched_tokens = [t for t in tokens if t in haystack]
    match_count, observed_state = _selector_match_count(selector, state_html)
    unique = match_count == 1

    return {
        "selector": selector,
        "origin": "observed_in_dom" if match_count > 0 else "rejected",
        "state": observed_state or item.get("state"),
        "match_count": match_count,
        "is_unique": unique,
        "uniqueness_explanation": "selector único" if unique else f"selector con {match_count} matches",
        "outer_html_excerpt": item.get("outer_html_excerpt"),
        "visible_text": item.get("text"),
        "attributes": {
            "id": item.get("id"),
            "class_list": item.get("class_list"),
            "href": item.get("href"),
            "aria_label": item.get("aria_label"),
            "title": item.get("title"),
            "tag": item.get("tag"),
        },
        "matched_tokens": matched_tokens,
        "score": len(matched_tokens) * 10 + (15 if unique else 0) + (5 if item.get("is_visible") else 0),
        "closest_supported": _closest_compatible(selector, item, state_html, observed_state),
    }


def propose_selectors(measurement_case: dict[str, Any], dom_snapshot: dict[str, Any]) -> dict[str, Any]:
    state_html = dom_snapshot.get("state_html") or {}
    inventory = dom_snapshot.get("clickable_inventory") or []
    inventory = [item for item in inventory if item.get("is_clickable")]

    if not state_html or not inventory:
        for interaction in measurement_case.get("interacciones", []):
            interaction["selector_candidato"] = None
            interaction["selector_activador"] = None
            interaction.setdefault("warnings", []).append(
                "Sin inventario de clickables observado en DOM; selector en null y human_review_required=true."
            )
        return {
            "status": "no_inventory",
            "measurement_case": measurement_case,
            "warnings": ["No hay inventario de clickables del DOM renderizado."],
            "clickable_inventory": inventory,
            "selector_evidence": [
                {
                    "index": idx,
                    "selector_origin": "rejected",
                    "human_review_required": True,
                }
                for idx, _ in enumerate(measurement_case.get("interacciones", []), start=1)
            ],
        }

    selector_evidence: list[dict[str, Any]] = []

    for index, interaction in enumerate(measurement_case.get("interacciones", []), start=1):
        interaction.setdefault("warnings", [])
        traces: list[dict[str, Any]] = []

        for item in inventory:
            for selector in item.get("selector_candidates") or []:
                evidence = _candidate_evidence(
                    interaction=interaction,
                    item=item,
                    selector=str(selector),
                    state_html=state_html,
                )
                traces.append(evidence)

        traces = [t for t in traces if t.get("match_count", 0) > 0]
        traces.sort(key=lambda t: (int(t.get("score", 0)), int(t.get("match_count", 0) == 1)), reverse=True)

        chosen = traces[0] if traces else None
        if not chosen:
            interaction["selector_candidato"] = None
            interaction["selector_activador"] = None
            interaction["match_count"] = None
            interaction["warnings"].append(
                "No se encontró selector observado en DOM para esta interacción; human_review_required=true."
            )
            selector_evidence.append(
                {
                    "index": index,
                    "selector": None,
                    "selector_origin": "rejected",
                    "human_review_required": True,
                    "candidates_considered": len(traces),
                    "candidates": [],
                }
            )
            continue

        selector = chosen["selector"]
        interaction["selector_candidato"] = selector
        interaction["selector_activador"] = f"{selector}, {selector} *"
        interaction["match_count"] = chosen["match_count"]
        if chosen["match_count"] != 1:
            interaction["warnings"].append(
                f"Selector observado en DOM pero no único ({chosen['match_count']} matches); revisar manualmente."
            )

        selector_evidence.append(
            {
                "index": index,
                "selector": selector,
                "selector_origin": "observed_in_dom",
                "human_review_required": chosen["match_count"] != 1,
                "chosen": chosen,
                "candidates_considered": len(traces),
                "candidates": traces[:10],
            }
        )

    return {
        "status": "ok",
        "measurement_case": measurement_case,
        "warnings": [],
        "clickable_inventory": inventory,
        "selector_evidence": selector_evidence,
    }
