"""Selector proposal logic with strict grounding and explicit provenance."""

from __future__ import annotations

import re
from typing import Any

from bs4 import BeautifulSoup
from bs4.element import Tag

from core.processing.selectors.manual_hints import MANUAL_GOLDEN_HINT_SOURCE
from core.processing.selectors.safety import (
    container_match_limit,
    group_match_limit,
    is_unsafe_group_selector,
    selector_safety_blockers,
    useful_visible_text,
)

NODE_ID_ATTR = "data-gtm-mvp-node-id"
SELECTOR_ORIGIN_RENDERED = "observed_rendered_dom"
SELECTOR_ORIGIN_FALLBACK = "raw_html_fallback"
SELECTOR_ORIGIN_REJECTED = "rejected"
SELECTOR_SOURCE_DETERMINISTIC = "deterministic"
SELECTOR_SOURCE_AI_RERANK = "ai_rerank"
SELECTOR_TYPE_WEIGHTS = {
    "id": 100,
    "data": 80,
    "aria": 70,
    "href": 60,
    "class": 35,
    "tag": 5,
}
STATEFUL_CLASS_TOKENS = (
    "active",
    "current",
    "selected",
    "open",
    "show",
    "next",
    "prev",
)


def _normalize(text: str | None) -> str:
    if not text:
        return ""
    cleaned = text.lower().strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    replacements = {
        "á": "a",
        "é": "e",
        "í": "i",
        "ó": "o",
        "ú": "u",
        "ü": "u",
        "ñ": "n",
        "¿": "",
        "Ã¡": "a",
        "Ã©": "e",
        "Ã­": "i",
        "Ã³": "o",
        "Ãº": "u",
        "Ã¼": "u",
        "Ã±": "n",
        "Â¿": "",
        "?": "",
    }
    for src, dst in replacements.items():
        cleaned = cleaned.replace(src, dst)
    return cleaned


def _tokenize(value: str | None) -> list[str]:
    normalized = _normalize(value)
    if not normalized:
        return []
    stopwords = {
        "de",
        "la",
        "el",
        "los",
        "las",
        "y",
        "en",
        "del",
        "para",
        "con",
        "por",
        "una",
        "uno",
        "unos",
        "unas",
        "al",
    }
    return [token for token in re.split(r"[^a-z0-9]+", normalized) if len(token) >= 3 and token not in stopwords]


def _normalized_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if isinstance(item, str) and item.strip()]


def _interaction_tokens(interaction: dict[str, Any]) -> list[str]:
    tokens: list[str] = []
    for field in ("texto_referencia", "elemento", "ubicacion", "flujo", "tipo_evento", "group_context", "zone_hint"):
        tokens.extend(_tokenize(interaction.get(field)))
    for value in _normalized_list(interaction.get("element_variants")):
        tokens.extend(_tokenize(value))
    for value in _normalized_list(interaction.get("title_variants")):
        tokens.extend(_tokenize(value))
    return list(dict.fromkeys(tokens))


def _selector_type(selector: str) -> str:
    if selector.startswith("#"):
        return "id"
    if "[data-" in selector:
        return "data"
    if "[aria-" in selector:
        return "aria"
    if "[href=" in selector:
        return "href"
    if "." in selector:
        return "class"
    return "tag"


def _expected_group_variants(interaction: dict[str, Any]) -> list[str]:
    return list(
        dict.fromkeys(
            [
                *_normalized_list(interaction.get("element_variants")),
                *_normalized_list(interaction.get("title_variants")),
            ]
        )
    )


def _selector_match_count(selector: str, soups: dict[str, BeautifulSoup]) -> tuple[int, str | None]:
    best_count = 0
    best_state: str | None = None
    for state, soup in soups.items():
        try:
            count = len(soup.select(selector))
        except Exception:
            count = 0
        if count > best_count:
            best_count = count
            best_state = state
    return best_count, best_state


def _select_matches(selector: str, soups: dict[str, BeautifulSoup], state: str | None = None) -> tuple[list[Tag], str | None]:
    if state and state in soups:
        try:
            return list(soups[state].select(selector)), state
        except Exception:
            return [], state
    count, observed_state = _selector_match_count(selector, soups)
    if not observed_state or count == 0:
        return [], observed_state
    try:
        return list(soups[observed_state].select(selector)), observed_state
    except Exception:
        return [], observed_state


def _tag_visible_text(tag: Tag) -> str:
    return re.sub(r"\s+", " ", tag.get_text(" ", strip=True)).strip()


def _selector_parent(selector: str) -> str | None:
    clean = selector.strip()
    if "," in clean:
        parents = [_selector_parent(part.strip()) for part in clean.split(",") if part.strip()]
        parents = [parent for parent in parents if parent]
        return ", ".join(parents) if parents else None
    for separator in (" > ", " "):
        if separator in clean:
            parent = clean.rsplit(separator, 1)[0].strip()
            return parent or None
    return None


def _runtime_flags(
    selector: str,
    item: dict[str, Any],
    soups: dict[str, BeautifulSoup],
    observed_state: str | None,
) -> dict[str, Any]:
    state = observed_state or item.get("state") or next(iter(soups.keys()), None)
    node_id = item.get("node_id")
    if not state or not node_id or state not in soups:
        return {
            "exists_in_dom": False,
            "matches_candidate_node": False,
            "closest_runtime_supported": False,
            "click_grounded": False,
        }

    soup = soups[state]
    try:
        matches = soup.select(selector)
    except Exception:
        matches = []
    exists_in_dom = bool(matches)

    candidate_node = soup.select_one(f'[{NODE_ID_ATTR}="{node_id}"]')
    matches_candidate_node = candidate_node in matches if candidate_node else False

    closest_runtime_supported = False
    if candidate_node:
        if matches_candidate_node:
            closest_runtime_supported = True
        else:
            parent = candidate_node.parent
            while isinstance(parent, Tag):
                if parent in matches:
                    closest_runtime_supported = True
                    break
                parent = parent.parent

    click_grounded = bool(
        exists_in_dom
        and matches_candidate_node
        and closest_runtime_supported
        and item.get("is_clickable")
    )
    return {
        "exists_in_dom": exists_in_dom,
        "matches_candidate_node": matches_candidate_node,
        "closest_runtime_supported": closest_runtime_supported,
        "click_grounded": click_grounded,
    }


def _candidate_alignment(interaction: dict[str, Any], item: dict[str, Any]) -> dict[str, Any]:
    tokens = _interaction_tokens(interaction)
    direct_haystack = _normalize(
        " ".join(
            [
                str(item.get("text") or ""),
                str(item.get("aria_label") or ""),
                str(item.get("title") or ""),
                str(item.get("href") or ""),
                str(item.get("id") or ""),
            ]
        )
    )
    context_haystack = _normalize(
        " ".join(
            [
                str(item.get("context_text") or ""),
                " ".join(
                    " ".join(
                        [
                            str(ancestor.get("tag") or ""),
                            str(ancestor.get("id") or ""),
                            " ".join(ancestor.get("classes") or []),
                        ]
                    )
                    for ancestor in (item.get("ancestors") or [])
                ),
            ]
        )
    )
    matched_direct_tokens = [token for token in tokens if token in direct_haystack]
    matched_context_tokens = [token for token in tokens if token not in matched_direct_tokens and token in context_haystack]

    exact_phrase_match = False
    for field in ("texto_referencia", "elemento"):
        normalized = _normalize(interaction.get(field))
        if normalized and len(normalized) >= 4:
            if normalized in direct_haystack or normalized in context_haystack:
                exact_phrase_match = True
                break

    alignment_score = len(matched_direct_tokens) * 35 + len(matched_context_tokens) * 10 + (30 if exact_phrase_match else 0)
    has_minimum_alignment = bool(matched_direct_tokens or exact_phrase_match)

    return {
        "tokens": tokens,
        "matched_tokens": list(dict.fromkeys([*matched_direct_tokens, *matched_context_tokens])),
        "matched_direct_tokens": matched_direct_tokens,
        "matched_context_tokens": matched_context_tokens,
        "exact_phrase_match": exact_phrase_match,
        "alignment_score": alignment_score,
        "has_minimum_alignment": has_minimum_alignment,
    }


def _candidate_origin(item: dict[str, Any], dom_snapshot: dict[str, Any]) -> str:
    source = str(item.get("source") or "")
    if source == SELECTOR_ORIGIN_FALLBACK or dom_snapshot.get("render_engine") == "raw_html_fallback":
        return SELECTOR_ORIGIN_FALLBACK
    if source == SELECTOR_ORIGIN_RENDERED or dom_snapshot.get("render_engine") == "playwright_multi_state":
        return SELECTOR_ORIGIN_RENDERED
    return SELECTOR_ORIGIN_REJECTED


def _candidate_evidence(
    *,
    interaction: dict[str, Any],
    item: dict[str, Any],
    selector: str,
    soups: dict[str, BeautifulSoup],
    dom_snapshot: dict[str, Any],
) -> dict[str, Any]:
    origin = _candidate_origin(item, dom_snapshot)
    selector_type = _selector_type(selector)
    match_count, observed_state = _selector_match_count(selector, soups)
    runtime_flags = _runtime_flags(selector, item, soups, observed_state)
    alignment = _candidate_alignment(interaction, item)
    generic_penalty = 90 if selector_type == "tag" else 0
    ambiguity_penalty = 25 if match_count > 1 else 0
    origin_penalty = 120 if origin == SELECTOR_ORIGIN_FALLBACK else 0
    score = (
        alignment["alignment_score"]
        + SELECTOR_TYPE_WEIGHTS.get(selector_type, 0)
        + (10 if runtime_flags["click_grounded"] else 0)
        + (15 if match_count == 1 else 0)
        - generic_penalty
        - ambiguity_penalty
        - origin_penalty
    )
    promotion_blockers: list[str] = []

    if origin != SELECTOR_ORIGIN_RENDERED:
        promotion_blockers.append("selector no proviene de DOM renderizado verificado")
    if match_count == 0:
        promotion_blockers.append("selector no existe en DOM observado")
    if match_count != 1:
        promotion_blockers.append(f"selector ambiguo ({match_count} matches)")
    if selector_type == "tag":
        promotion_blockers.append("selector genérico de tag no se autopromueve")
    if not alignment["has_minimum_alignment"]:
        promotion_blockers.append("sin evidencia mínima de alineación interacción-nodo")
    if not runtime_flags["matches_candidate_node"]:
        promotion_blockers.append("selector no apunta al nodo candidato observado")
    if not runtime_flags["closest_runtime_supported"]:
        promotion_blockers.append("selector no demuestra soporte real para event.target.closest")
    if not runtime_flags["click_grounded"]:
        promotion_blockers.append("selector no queda click_grounded")

    can_promote = not promotion_blockers

    return {
        "selector": selector,
        "selector_type": selector_type,
        "selector_source": "automatic",
        "selector_origin": origin,
        "state": observed_state or item.get("state"),
        "match_count": match_count,
        "is_unique": match_count == 1,
        "uniqueness_explanation": "selector único" if match_count == 1 else f"selector con {match_count} matches",
        "outer_html_excerpt": item.get("outer_html_excerpt"),
        "visible_text": item.get("text"),
        "context_text": item.get("context_text"),
        "attributes": {
            "id": item.get("id"),
            "class_list": item.get("class_list"),
            "href": item.get("href"),
            "aria_label": item.get("aria_label"),
            "title": item.get("title"),
            "tag": item.get("tag"),
            "node_id": item.get("node_id"),
        },
        "matched_tokens": alignment["matched_tokens"],
        "matched_direct_tokens": alignment["matched_direct_tokens"],
        "matched_context_tokens": alignment["matched_context_tokens"],
        "has_minimum_alignment": alignment["has_minimum_alignment"],
        "alignment_score": alignment["alignment_score"],
        "specificity_score": SELECTOR_TYPE_WEIGHTS.get(selector_type, 0),
        "score": score,
        "exists_in_dom": runtime_flags["exists_in_dom"],
        "matches_candidate_node": runtime_flags["matches_candidate_node"],
        "closest_runtime_supported": runtime_flags["closest_runtime_supported"],
        "click_grounded": runtime_flags["click_grounded"],
        "promotion_blockers": promotion_blockers,
        "can_promote": can_promote,
    }


def _selector_trace_summary(selector_evidence: list[dict[str, Any]]) -> dict[str, Any]:
    summary = {
        "total_interactions": len(selector_evidence),
        "promoted_selectors": 0,
        "human_review_required": 0,
        "origins": {
            SELECTOR_ORIGIN_RENDERED: 0,
            SELECTOR_ORIGIN_FALLBACK: 0,
            SELECTOR_ORIGIN_REJECTED: 0,
        },
    }
    for evidence in selector_evidence:
        origin = evidence.get("selector_origin") or SELECTOR_ORIGIN_REJECTED
        summary["origins"][origin] = summary["origins"].get(origin, 0) + 1
        if evidence.get("promoted"):
            summary["promoted_selectors"] += 1
        if evidence.get("human_review_required"):
            summary["human_review_required"] += 1
    return summary


def _stable_classes(classes: list[str] | None) -> list[str]:
    stable: list[str] = []
    for value in classes or []:
        if not value or len(value) <= 2:
            continue
        normalized = value.lower()
        if any(token in normalized for token in STATEFUL_CLASS_TOKENS):
            continue
        stable.append(value)
    return stable


def _item_direct_haystack(item: dict[str, Any]) -> str:
    return _normalize(
        " ".join(
            [
                str(item.get("text") or ""),
                str(item.get("aria_label") or ""),
                str(item.get("title") or ""),
                str(item.get("href") or ""),
                str(item.get("id") or ""),
            ]
        )
    )


def _item_context_haystack(item: dict[str, Any]) -> str:
    return _normalize(
        " ".join(
            [
                str(item.get("context_text") or ""),
                " ".join(
                    " ".join(
                        [
                            str(ancestor.get("tag") or ""),
                            str(ancestor.get("id") or ""),
                            " ".join(ancestor.get("classes") or []),
                        ]
                    )
                    for ancestor in (item.get("ancestors") or [])
                ),
            ]
        )
    )


def _variant_matches(variants: list[str], direct_haystack: str, context_haystack: str) -> tuple[list[str], list[str]]:
    direct_matches: list[str] = []
    context_matches: list[str] = []
    for variant in variants:
        normalized = _normalize(variant)
        if not normalized:
            continue
        if normalized in direct_haystack:
            direct_matches.append(variant)
        elif normalized in context_haystack:
            context_matches.append(variant)
    return direct_matches, context_matches


def _zone_alignment_score(interaction: dict[str, Any], item: dict[str, Any]) -> int:
    zone_hint = _normalize(interaction.get("zone_hint"))
    group_context = _normalize(interaction.get("group_context"))
    haystack = _item_context_haystack(item)
    score = 0

    if zone_hint == "header-menu" and ("header-menu" in haystack or "menu-" in haystack):
        score += 4
    if zone_hint == "shortcut-tabs" and ("desktop-submenu" in haystack or "submenu" in haystack):
        score += 4
    if zone_hint == "faq-list" and ("lista-preguntas" in haystack or "preguntas-frecuentes" in haystack):
        score += 4
    if zone_hint == "card-grid" and any(token in haystack for token in ("card-footer", "btn-products", "swiper", " card ")):
        score += 4

    if group_context == "card_collection" and any(token in haystack for token in ("card", "swiper", "btn-products")):
        score += 2
    if group_context == "faq_collection" and any(token in haystack for token in ("preguntas", "faq")):
        score += 2
    if group_context == "top_navigation" and "header-menu" in haystack:
        score += 2
    if group_context == "shortcut_collection" and "submenu" in haystack:
        score += 2

    for token in _tokenize(interaction.get("ubicacion")):
        if token and token in haystack:
            score += 1

    return score


def _group_item_alignment(interaction: dict[str, Any], item: dict[str, Any]) -> dict[str, Any]:
    direct_haystack = _item_direct_haystack(item)
    context_haystack = _item_context_haystack(item)
    element_variants = _normalized_list(interaction.get("element_variants"))
    title_variants = _normalized_list(interaction.get("title_variants"))
    matched_element_direct, matched_element_context = _variant_matches(element_variants, direct_haystack, context_haystack)
    matched_title_direct, matched_title_context = _variant_matches(title_variants, direct_haystack, context_haystack)
    zone_score = _zone_alignment_score(interaction, item)

    matched_variants = list(
        dict.fromkeys(
            [*matched_element_direct, *matched_element_context, *matched_title_direct, *matched_title_context]
        )
    )
    score = (
        len(matched_element_direct) * 45
        + len(matched_element_context) * 20
        + len(matched_title_direct) * 30
        + len(matched_title_context) * 15
        + zone_score * 12
        + (5 if item.get("is_visible") else 0)
    )
    qualifies = bool(matched_variants)

    return {
        "matched_variants": matched_variants,
        "matched_element_direct": matched_element_direct,
        "matched_element_context": matched_element_context,
        "matched_title_direct": matched_title_direct,
        "matched_title_context": matched_title_context,
        "zone_score": zone_score,
        "score": score,
        "qualifies": qualifies,
    }


def _item_role(item: dict[str, Any]) -> str:
    outer_html = str(item.get("outer_html_excerpt") or "")
    match = re.search(r"\brole=[\"']([^\"']+)[\"']", outer_html, flags=re.IGNORECASE)
    return _normalize(match.group(1)) if match else ""


def _allowed_group_click_target(interaction: dict[str, Any], item: dict[str, Any]) -> bool:
    tag = str(item.get("tag") or "").strip().lower()
    role = _item_role(item)
    group_context = _normalize(interaction.get("group_context"))
    if group_context in {"top_navigation", "menu"}:
        return tag in {"a", "button"}
    if group_context == "shortcut_collection":
        return tag in {"a", "button"} or role == "tab"
    if group_context == "faq_collection":
        return tag == "a"
    if group_context == "card_collection":
        return tag in {"a", "button"}
    return tag in {"a", "button"} or role in {"button", "tab"}


def _alignment_allowed_for_group_context(interaction: dict[str, Any], item: dict[str, Any], alignment: dict[str, Any]) -> bool:
    group_context = _normalize(interaction.get("group_context"))
    if group_context in {"top_navigation", "menu", "shortcut_collection"}:
        return bool(alignment.get("matched_element_direct"))
    if group_context == "faq_collection":
        return bool(alignment.get("matched_element_direct")) and "/preguntas-frecuentes" in str(item.get("href") or "")
    if group_context == "card_collection":
        return bool(
            alignment.get("matched_element_direct")
            or alignment.get("matched_title_direct")
            or alignment.get("matched_title_context")
        )
    return bool(alignment.get("matched_variants"))


def _minimum_group_variant_coverage(interaction: dict[str, Any]) -> int:
    group_context = _normalize(interaction.get("group_context"))
    variants = _expected_group_variants(interaction)
    if not variants:
        return 1
    if group_context in {"top_navigation", "menu"}:
        return min(2, len(_normalized_list(interaction.get("element_variants"))) or len(variants))
    if group_context == "shortcut_collection":
        return min(2, len(_normalized_list(interaction.get("element_variants"))) or len(variants))
    if group_context == "faq_collection":
        return min(2, len(_normalized_list(interaction.get("element_variants"))) or len(variants))
    if group_context == "card_collection":
        return 1
    return 1


def _href_group_selector(interaction: dict[str, Any], items: list[dict[str, Any]]) -> str | None:
    tag_values = {str(item.get("tag") or "").strip().lower() for item in items}
    if tag_values != {"a"}:
        return None
    hrefs = [str(item.get("href") or "").strip() for item in items if str(item.get("href") or "").strip()]
    if len(hrefs) < 2:
        return None

    group_context = _normalize(interaction.get("group_context"))
    if group_context == "faq_collection" and all("/centro-de-ayuda/preguntas-frecuentes/" in href for href in hrefs):
        return 'a[href*="/centro-de-ayuda/preguntas-frecuentes/"]'

    common_prefix = hrefs[0]
    for href in hrefs[1:]:
        while common_prefix and not href.startswith(common_prefix):
            common_prefix = common_prefix[:-1]
    common_prefix = common_prefix.rstrip("-_/")
    if len(common_prefix) >= 16 and common_prefix not in {"/personas", "https://www.bancolombia.com"}:
        return f'a[href^="{common_prefix}"]'
    return None


def _matched_variants_from_text(interaction: dict[str, Any], *texts: str) -> list[str]:
    haystack = _normalize(" ".join(text for text in texts if text))
    variants = _expected_group_variants(interaction)
    return [variant for variant in variants if _normalize(variant) and _normalize(variant) in haystack]


def _hint_container_selector(selector: str, interaction: dict[str, Any]) -> str | None:
    if "," in selector:
        roots = []
        for part in selector.split(","):
            ids = re.findall(r"#([A-Za-z_][\w-]*)", part)
            if ids:
                roots.append(f"#{ids[0]}")
            else:
                parent = _selector_parent(part.strip())
                if parent:
                    roots.append(parent)
        return ", ".join(dict.fromkeys(roots)) if roots else None

    group_context = _normalize(interaction.get("group_context"))
    if group_context == "faq_collection" and ".lista-preguntas" in selector:
        return ".lista-preguntas"
    parent = _selector_parent(selector)
    return parent if parent and not is_unsafe_group_selector(parent) else None


def _hint_context_text(matches: list[Tag], container_selector: str | None, soup: BeautifulSoup | None) -> list[str]:
    values: list[str] = []
    containers: list[Tag] = []
    if container_selector and soup is not None:
        try:
            containers = list(soup.select(container_selector))
        except Exception:
            containers = []
    for match in matches:
        values.append(_tag_visible_text(match))
        container = next(
            (
                candidate
                for candidate in containers
                if candidate is match or any(parent is candidate for parent in match.parents)
            ),
            None,
        )
        if container is not None:
            values.append(_tag_visible_text(container))
        else:
            parent = match.parent
            if isinstance(parent, Tag):
                values.append(_tag_visible_text(parent))
    return values


def _card_mapping_from_hint(selector: str, interaction: dict[str, Any]) -> list[dict[str, str]]:
    element_variants = _normalized_list(interaction.get("element_variants"))
    title_variants = _normalized_list(interaction.get("title_variants"))
    mappings: list[dict[str, str]] = []
    parts = [part.strip() for part in selector.split(",") if part.strip()]
    for index, part in enumerate(parts):
        ids = re.findall(r"#([A-Za-z_][\w-]*)", part)
        if not ids:
            continue
        mapping: dict[str, str] = {
            "card_id": ids[0],
            "selector": part,
        }
        if index < len(element_variants):
            mapping["elemento"] = element_variants[index]
        if index < len(title_variants):
            mapping["tituloCard"] = title_variants[index]
        mappings.append(mapping)
    return mappings


def _manual_hint_evidence(
    *,
    interaction: dict[str, Any],
    selector: str,
    soups: dict[str, BeautifulSoup],
    hint_file: str | None,
) -> dict[str, Any]:
    selector = selector.strip()
    container_selector = _hint_container_selector(selector, interaction)
    item_matches, observed_state = _select_matches(selector, soups)
    soup = soups.get(observed_state) if observed_state else None
    container_match_count, _container_state = _selector_match_count(container_selector, soups) if container_selector else (0, None)
    item_match_count = len(item_matches)
    context_values = _hint_context_text(item_matches, container_selector, soup)
    matched_variants = _matched_variants_from_text(interaction, *context_values)
    expected_variants = _expected_group_variants(interaction)
    minimum_variant_coverage = _minimum_group_variant_coverage(interaction)
    item_match_limit = group_match_limit(len(expected_variants), len(matched_variants))
    promotion_blockers: list[str] = []
    promotion_blockers.extend(selector_safety_blockers(selector, role="item"))
    if not container_selector:
        promotion_blockers.append("manual_golden_hint sin contenedor estable derivable")
    elif is_unsafe_group_selector(container_selector):
        promotion_blockers.append(f"manual_golden_hint con contenedor no discriminante: {container_selector}")
    if item_match_count == 0:
        promotion_blockers.append("manual_golden_hint no existe en DOM renderizado")
    if item_match_count < 2:
        promotion_blockers.append("manual_golden_hint cubre menos de 2 items")
    if item_match_count > item_match_limit:
        promotion_blockers.append(f"match_count global excesivo para hint ({item_match_count})")
    if container_selector and container_match_count > container_match_limit():
        promotion_blockers.append(f"container_match_count excesivo para hint ({container_match_count})")
    if len(matched_variants) < minimum_variant_coverage:
        promotion_blockers.append(
            f"variant_coverage insuficiente para hint ({len(matched_variants)} < {minimum_variant_coverage})"
        )
    if not useful_visible_text(context_values):
        promotion_blockers.append("manual_golden_hint sin texto visible útil")

    group_context = _normalize(interaction.get("group_context"))
    if group_context == "card_collection" and "," not in selector:
        promotion_blockers.append("card_collection requiere selector_item compuesto para hints de cards")

    card_mapping = _card_mapping_from_hint(selector, interaction) if group_context == "card_collection" else []
    if group_context == "card_collection" and not card_mapping:
        promotion_blockers.append("card_collection sin mapping plan-based derivado del hint")

    can_promote = not promotion_blockers
    return {
        "selector": selector,
        "selector_type": _selector_type(selector),
        "selector_source": MANUAL_GOLDEN_HINT_SOURCE,
        "selector_origin": SELECTOR_ORIGIN_RENDERED if item_matches else SELECTOR_ORIGIN_REJECTED,
        "hint_file": hint_file,
        "state": observed_state,
        "match_count": item_match_count,
        "container_match_count": container_match_count,
        "selector_contenedor": container_selector,
        "selector_item": selector,
        "group_item_count": item_match_count,
        "candidate_group_item_count": item_match_count,
        "matched_variants": matched_variants,
        "variant_coverage": len(matched_variants),
        "minimum_variant_coverage": minimum_variant_coverage,
        "group_match_limit": item_match_limit,
        "outside_match_count": 0,
        "visible_text": context_values[:5],
        "context_text": context_values[:3],
        "attributes": {
            "node_ids": [match.get(NODE_ID_ATTR) for match in item_matches[:10] if match.get(NODE_ID_ATTR)],
        },
        "alignment_score": len(matched_variants) * 60,
        "specificity_score": SELECTOR_TYPE_WEIGHTS.get(_selector_type(selector), 0) + 20,
        "score": len(matched_variants) * 80 + item_match_count * 15 + 50,
        "exists_in_dom": bool(item_matches),
        "matches_candidate_node": bool(item_matches),
        "closest_runtime_supported": bool(item_matches),
        "click_grounded": bool(item_matches),
        "promotion_blockers": promotion_blockers,
        "can_promote": can_promote,
        "card_mapping": card_mapping,
        "outer_html_excerpt": [str(match)[:500] for match in item_matches[:3]],
        "uniqueness_explanation": (
            f"manual_golden_hint con {item_match_count} matches"
            if item_match_count
            else "manual_golden_hint sin matches"
        ),
    }


def _manual_hint_group_traces(
    *,
    interaction: dict[str, Any],
    soups: dict[str, BeautifulSoup],
    manual_selector_hints: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    selectors = list((manual_selector_hints or {}).get("selectors") or [])
    if not selectors:
        return []
    hint_file = (manual_selector_hints or {}).get("hint_file")
    group_context = _normalize(interaction.get("group_context"))
    traces: list[dict[str, Any]] = []

    if group_context == "card_collection":
        card_candidates = [
            selector
            for selector in selectors
            if re.search(r"#recomendado_\d+", selector) or "card-footer" in selector or "btn-outline-brand" in selector
        ]
        if card_candidates:
            traces.append(
                _manual_hint_evidence(
                    interaction=interaction,
                    selector=", ".join(card_candidates),
                    soups=soups,
                    hint_file=hint_file,
                )
            )
        return traces

    for selector in selectors:
        traces.append(
            _manual_hint_evidence(
                interaction=interaction,
                selector=selector,
                soups=soups,
                hint_file=hint_file,
            )
        )
    return traces


def _dedupe_items_by_node_id(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unique: dict[str, dict[str, Any]] = {}
    for item in items:
        node_id = str(item.get("node_id") or "")
        if not node_id:
            continue
        current = unique.get(node_id)
        if current is None:
            unique[node_id] = item
            continue
        current_visible = bool(current.get("is_visible"))
        next_visible = bool(item.get("is_visible"))
        if next_visible and not current_visible:
            unique[node_id] = item
    return list(unique.values())


def _ancestor_selector_candidates(item: dict[str, Any]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()
    for depth, ancestor in enumerate(item.get("ancestors") or [], start=1):
        tag = str(ancestor.get("tag") or "").strip().lower()
        if not tag:
            continue
        selector_options: list[tuple[str, int]] = []
        ancestor_id = ancestor.get("id")
        if ancestor_id:
            selector_options.append((f"#{ancestor_id}", 100))
        stable_classes = _stable_classes(ancestor.get("classes") or [])
        if stable_classes:
            selector_options.append((f"{tag}.{stable_classes[0]}", 35))
            if len(stable_classes) > 1:
                selector_options.append((f"{tag}.{stable_classes[0]}.{stable_classes[1]}", 45))

        for selector, specificity in selector_options:
            if selector in seen:
                continue
            seen.add(selector)
            candidates.append(
                {
                    "selector": selector,
                    "depth": depth,
                    "specificity_score": specificity,
                }
            )
    return candidates


def _common_ancestor_selectors(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidate_maps = []
    for item in items:
        item_map = {candidate["selector"]: candidate for candidate in _ancestor_selector_candidates(item)}
        if item_map:
            candidate_maps.append(item_map)
    if not candidate_maps:
        return []

    common = set(candidate_maps[0].keys())
    for item_map in candidate_maps[1:]:
        common &= set(item_map.keys())

    results: list[dict[str, Any]] = []
    for selector in common:
        specificity_score = max(item_map[selector]["specificity_score"] for item_map in candidate_maps)
        depth = min(item_map[selector]["depth"] for item_map in candidate_maps)
        results.append(
            {
                "selector": selector,
                "depth": depth,
                "specificity_score": specificity_score,
            }
        )
    return results


def _group_item_selector_candidates(
    container_selector: str,
    items: list[dict[str, Any]],
    interaction: dict[str, Any],
) -> list[str]:
    tags = {str(item.get("tag") or "").strip().lower() for item in items if item.get("tag")}
    tag = next(iter(tags), "")
    if not tag:
        return []

    class_sets = []
    for item in items:
        stable_classes = set(_stable_classes(item.get("class_list") or []))
        class_sets.append(stable_classes)
    common_classes = set.intersection(*class_sets) if class_sets else set()

    selectors: list[str] = []
    href_selector = _href_group_selector(interaction, items)
    if href_selector:
        selectors.append(f"{container_selector} {href_selector}")

    common_selector_candidates: set[str] | None = None
    for item in items:
        item_selectors = {str(selector).strip() for selector in (item.get("selector_candidates") or []) if selector}
        common_selector_candidates = item_selectors if common_selector_candidates is None else common_selector_candidates & item_selectors
    for selector in sorted(common_selector_candidates or []):
        if is_unsafe_group_selector(selector):
            continue
        selectors.append(f"{container_selector} {selector}")

    ordered_common = sorted(common_classes)
    if ordered_common:
        selectors.append(f"{container_selector} {tag}.{ordered_common[0]}")
        if len(ordered_common) > 1:
            selectors.append(f"{container_selector} {tag}.{ordered_common[0]}.{ordered_common[1]}")

    unique: list[str] = []
    seen: set[str] = set()
    for selector in selectors:
        if is_unsafe_group_selector(selector):
            continue
        if selector in seen:
            continue
        seen.add(selector)
        unique.append(selector)
    return unique


def _group_origin(items: list[dict[str, Any]], dom_snapshot: dict[str, Any]) -> str:
    origins = {_candidate_origin(item, dom_snapshot) for item in items}
    if origins == {SELECTOR_ORIGIN_RENDERED}:
        return SELECTOR_ORIGIN_RENDERED
    if SELECTOR_ORIGIN_FALLBACK in origins:
        return SELECTOR_ORIGIN_FALLBACK
    return SELECTOR_ORIGIN_REJECTED


def _group_candidate_evidence(
    *,
    interaction: dict[str, Any],
    matched_items: list[dict[str, Any]],
    container_selector: str,
    item_selector: str,
    soups: dict[str, BeautifulSoup],
    dom_snapshot: dict[str, Any],
) -> dict[str, Any]:
    unique_items = _dedupe_items_by_node_id(matched_items)
    origin = _group_origin(unique_items, dom_snapshot)
    item_selector_type = _selector_type(item_selector)
    container_match_count, container_state = _selector_match_count(container_selector, soups)
    item_match_count, item_state = _selector_match_count(item_selector, soups)
    observed_state = item_state or container_state
    soup = soups.get(observed_state) if observed_state else None

    item_matches: list[Tag] = []
    container_matches: list[Tag] = []
    if soup is not None:
        try:
            item_matches = soup.select(item_selector)
        except Exception:
            item_matches = []
        try:
            container_matches = soup.select(container_selector)
        except Exception:
            container_matches = []

    matched_node_ids = {
        str(match.get(NODE_ID_ATTR))
        for match in item_matches
        if isinstance(match, Tag) and match.get(NODE_ID_ATTR)
    }
    covered_items = [item for item in unique_items if str(item.get("node_id")) in matched_node_ids]
    matched_variants = list(
        dict.fromkeys(
            variant
            for item in covered_items
            for variant in (item.get("__group_alignment__") or {}).get("matched_variants", [])
        )
    )
    average_zone_score = round(
        (
            sum(int((item.get("__group_alignment__") or {}).get("zone_score") or 0) for item in unique_items)
            / len(unique_items)
        ),
        2,
    ) if unique_items else 0.0

    expected_variants = _expected_group_variants(interaction)
    minimum_variant_coverage = _minimum_group_variant_coverage(interaction)
    item_match_limit = group_match_limit(len(expected_variants), len(unique_items))
    group_context = _normalize(interaction.get("group_context"))
    promotion_blockers: list[str] = []
    promotion_blockers.extend(selector_safety_blockers(item_selector, role="item"))
    promotion_blockers.extend(selector_safety_blockers(container_selector, role="contenedor"))
    if origin != SELECTOR_ORIGIN_RENDERED:
        promotion_blockers.append("grupo no proviene de DOM renderizado verificado")
    if container_match_count == 0:
        promotion_blockers.append("selector de contenedor no existe en DOM observado")
    if container_match_count > container_match_limit():
        promotion_blockers.append(f"container_match_count excesivo ({container_match_count})")
    if item_match_count == 0:
        promotion_blockers.append("selector de item no existe en DOM observado")
    if item_match_count > item_match_limit:
        promotion_blockers.append(f"match_count global excesivo para grupo ({item_match_count})")
    if item_match_count < 2:
        promotion_blockers.append("selector de item colapsa el grupo a menos de 2 matches")
    if len(covered_items) < 2:
        promotion_blockers.append("selector de item no cubre suficientes nodos candidatos del grupo")
    if not covered_items:
        promotion_blockers.append("selector de item no demuestra soporte real para event.target.closest")
    if len(matched_variants) < minimum_variant_coverage:
        promotion_blockers.append(
            f"variant_coverage insuficiente ({len(matched_variants)} < {minimum_variant_coverage})"
        )
    if not useful_visible_text([item.get("text") for item in covered_items]):
        promotion_blockers.append("visible_text vacío o sin señales útiles")
    outside_matches = max(0, item_match_count - len(covered_items))
    if outside_matches > max(2, len(covered_items)):
        promotion_blockers.append(
            f"selector_item cubre nodos fuera del bloque esperado ({outside_matches} matches externos)"
        )
    if group_context == "faq_collection" and "href" not in item_selector.lower():
        promotion_blockers.append("faq_collection requiere selector_item con href discriminante")
    title_variants = set(_normalized_list(interaction.get("title_variants")))
    if group_context == "card_collection" and title_variants and not (set(matched_variants) & title_variants):
        promotion_blockers.append("card_collection sin título de card resuelto con confianza")

    can_promote = not promotion_blockers
    score = (
        len(matched_variants) * 60
        + len(covered_items) * 25
        + SELECTOR_TYPE_WEIGHTS.get(_selector_type(container_selector), 0)
        + SELECTOR_TYPE_WEIGHTS.get(item_selector_type, 0)
        + int(average_zone_score * 10)
        + (10 if container_match_count >= 1 else 0)
    )

    return {
        "selector": item_selector,
        "selector_type": item_selector_type,
        "selector_source": "automatic",
        "selector_origin": origin,
        "state": observed_state,
        "match_count": item_match_count,
        "container_match_count": container_match_count,
        "selector_contenedor": container_selector,
        "selector_item": item_selector,
        "group_item_count": len(covered_items),
        "candidate_group_item_count": len(unique_items),
        "matched_variants": matched_variants,
        "variant_coverage": len(matched_variants),
        "minimum_variant_coverage": minimum_variant_coverage,
        "group_match_limit": item_match_limit,
        "outside_match_count": outside_matches,
        "average_zone_score": average_zone_score,
        "visible_text": [item.get("text") for item in covered_items[:5]],
        "context_text": [item.get("context_text") for item in covered_items[:3]],
        "attributes": {
            "tag": next((item.get("tag") for item in covered_items if item.get("tag")), None),
            "node_ids": [item.get("node_id") for item in covered_items[:10]],
        },
        "alignment_score": len(matched_variants) * 50 + int(average_zone_score * 10),
        "specificity_score": SELECTOR_TYPE_WEIGHTS.get(item_selector_type, 0),
        "score": score,
        "exists_in_dom": bool(item_matches),
        "matches_candidate_node": len(covered_items) >= 2,
        "closest_runtime_supported": len(covered_items) >= 2,
        "click_grounded": len(covered_items) >= 2 and origin == SELECTOR_ORIGIN_RENDERED,
        "promotion_blockers": promotion_blockers,
        "can_promote": can_promote,
        "outer_html_excerpt": [item.get("outer_html_excerpt") for item in covered_items[:3]],
        "uniqueness_explanation": (
            f"selector grupal con {item_match_count} matches"
            if item_match_count
            else "selector grupal sin matches"
        ),
    }


def _select_single_interaction(
    *,
    interaction: dict[str, Any],
    inventory: list[dict[str, Any]],
    soups: dict[str, BeautifulSoup],
    dom_snapshot: dict[str, Any],
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    traces: list[dict[str, Any]] = []
    for item in inventory:
        seen: set[str] = set()
        for selector in item.get("selector_candidates") or []:
            selector_text = str(selector)
            if selector_text in seen:
                continue
            seen.add(selector_text)
            traces.append(
                _candidate_evidence(
                    interaction=interaction,
                    item=item,
                    selector=selector_text,
                    soups=soups,
                    dom_snapshot=dom_snapshot,
                )
            )

    traces = [trace for trace in traces if trace.get("exists_in_dom")]
    traces.sort(
        key=lambda trace: (
            int(bool(trace.get("can_promote"))),
            int(trace.get("alignment_score", 0)),
            int(trace.get("specificity_score", 0)),
            int(bool(trace.get("click_grounded"))),
            -int(trace.get("match_count", 0)),
        ),
        reverse=True,
    )
    return (traces[0] if traces else None), traces


def _select_group_interaction(
    *,
    interaction: dict[str, Any],
    inventory: list[dict[str, Any]],
    soups: dict[str, BeautifulSoup],
    dom_snapshot: dict[str, Any],
    manual_selector_hints: dict[str, Any] | None = None,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    aligned_items: list[dict[str, Any]] = []
    for item in inventory:
        if not _allowed_group_click_target(interaction, item):
            continue
        alignment = _group_item_alignment(interaction, item)
        if not alignment["qualifies"]:
            continue
        if not _alignment_allowed_for_group_context(interaction, item, alignment):
            continue
        enriched = dict(item)
        enriched["__group_alignment__"] = alignment
        aligned_items.append(enriched)

    unique_items = _dedupe_items_by_node_id(aligned_items)
    traces: list[dict[str, Any]] = []

    if len(unique_items) >= 2:
        ancestor_candidates = _common_ancestor_selectors(unique_items)
        for ancestor in ancestor_candidates:
            container_selector = ancestor["selector"]
            if is_unsafe_group_selector(container_selector):
                continue
            for item_selector in _group_item_selector_candidates(container_selector, unique_items, interaction):
                traces.append(
                    _group_candidate_evidence(
                        interaction=interaction,
                        matched_items=unique_items,
                        container_selector=container_selector,
                        item_selector=item_selector,
                        soups=soups,
                        dom_snapshot=dom_snapshot,
                    )
                )

    traces.extend(
        _manual_hint_group_traces(
            interaction=interaction,
            soups=soups,
            manual_selector_hints=manual_selector_hints,
        )
    )

    traces.sort(
        key=lambda trace: (
            int(bool(trace.get("can_promote"))),
            int(trace.get("selector_source") == MANUAL_GOLDEN_HINT_SOURCE),
            int(trace.get("variant_coverage", 0)),
            int(trace.get("group_item_count", 0)),
            int(trace.get("specificity_score", 0)),
            int(trace.get("score", 0)),
        ),
        reverse=True,
    )
    return (traces[0] if traces else None), traces


def _safe_ai_text(value: Any, limit: int = 700) -> Any:
    if isinstance(value, str):
        return value[:limit]
    if isinstance(value, list):
        return [_safe_ai_text(item, limit) for item in value[:10]]
    if isinstance(value, dict):
        return {str(key): _safe_ai_text(item, limit) for key, item in value.items()}
    return value


def _ai_candidate_payload(candidate: dict[str, Any], interaction: dict[str, Any]) -> dict[str, Any]:
    safety_blockers: list[str] = []
    selector = candidate.get("selector_item") or candidate.get("selector")
    container_selector = candidate.get("selector_contenedor")
    safety_blockers.extend(selector_safety_blockers(selector, role="item"))
    if container_selector:
        safety_blockers.extend(selector_safety_blockers(container_selector, role="contenedor"))
    card_mapping = list(candidate.get("card_mapping") or [])
    return {
        "selector": candidate.get("selector"),
        "selector_source": candidate.get("selector_source"),
        "selector_origin": candidate.get("selector_origin"),
        "selector_item": candidate.get("selector_item"),
        "selector_contenedor": candidate.get("selector_contenedor"),
        "match_count": candidate.get("match_count"),
        "container_match_count": candidate.get("container_match_count"),
        "variant_coverage": candidate.get("variant_coverage"),
        "visible_text": _safe_ai_text(candidate.get("visible_text")),
        "outer_html_excerpt": _safe_ai_text(candidate.get("outer_html_excerpt")),
        "safety_blockers": list(dict.fromkeys(safety_blockers)),
        "promotion_blockers": _safe_ai_text(candidate.get("promotion_blockers") or []),
        "source": candidate.get("selector_source"),
        "origin": candidate.get("selector_origin"),
        "card_mapping": _safe_ai_text(card_mapping),
        "card_mapping_complete": _card_mapping_complete_for_ai(interaction, card_mapping),
        "matched_variants": _safe_ai_text(candidate.get("matched_variants") or []),
        "group_item_count": candidate.get("group_item_count"),
        "candidate_group_item_count": candidate.get("candidate_group_item_count"),
        "exists_in_dom": candidate.get("exists_in_dom"),
        "closest_runtime_supported": candidate.get("closest_runtime_supported"),
        "click_grounded": candidate.get("click_grounded"),
    }


def _build_ai_rerank_payload(
    *,
    case_id: str | None,
    interaction_index: int,
    interaction: dict[str, Any],
    traces: list[dict[str, Any]],
) -> dict[str, Any]:
    considered = [_ai_candidate_payload(trace, interaction) for trace in traces[:25]]
    allowed_selectors = []
    for trace in traces:
        for key in ("selector", "selector_item", "selector_contenedor"):
            value = trace.get(key)
            if value:
                allowed_selectors.append(str(value))
    return {
        "case_id": case_id,
        "interaction_index": interaction_index,
        "tipo_evento": interaction.get("tipo_evento"),
        "flujo": interaction.get("flujo"),
        "ubicacion": interaction.get("ubicacion"),
        "group_context": interaction.get("group_context"),
        "zone_hint": interaction.get("zone_hint"),
        "element_variants": interaction.get("element_variants") or [],
        "title_variants": interaction.get("title_variants") or [],
        "allowed_selectors": list(dict.fromkeys(allowed_selectors)),
        "candidates_considered": considered,
        "rejected_candidates": [item for item in considered if item.get("promotion_blockers")],
    }


def _selected_ai_candidate(ai_result: dict[str, Any], traces: list[dict[str, Any]]) -> dict[str, Any] | None:
    selected_values = {
        str(value).strip()
        for value in (
            ai_result.get("selected_selector"),
            ai_result.get("selected_item_selector"),
        )
        if value
    }
    if not selected_values:
        return None
    for trace in traces:
        trace_values = {
            str(value).strip()
            for value in (trace.get("selector"), trace.get("selector_item"))
            if value
        }
        if selected_values & trace_values:
            selected_container = str(ai_result.get("selected_container_selector") or "").strip()
            trace_container = str(trace.get("selector_contenedor") or "").strip()
            if selected_container and selected_container != trace_container:
                continue
            return trace
    return None


def _ai_allowed_to_override_blocker(blocker: str, *, has_card_mapping: bool) -> bool:
    normalized = _normalize(blocker)
    if not has_card_mapping:
        return False
    return "variant_coverage insuficiente" in normalized or "card_collection sin titulo" in normalized


def _card_mapping_complete_for_ai(interaction: dict[str, Any], card_mapping: list[dict[str, Any]]) -> bool:
    element_variants = set(_normalized_list(interaction.get("element_variants")))
    title_variants = set(_normalized_list(interaction.get("title_variants")))
    expected_count = max(len(element_variants), len(title_variants), 2)

    if len(card_mapping) < expected_count:
        return False
    if not all(mapping.get("card_id") and mapping.get("selector") for mapping in card_mapping):
        return False

    mapped_elements = {str(mapping.get("elemento")) for mapping in card_mapping if mapping.get("elemento")}
    mapped_titles = {str(mapping.get("tituloCard")) for mapping in card_mapping if mapping.get("tituloCard")}
    if element_variants and not element_variants.issubset(mapped_elements):
        return False
    if title_variants and not title_variants.issubset(mapped_titles):
        return False
    return True


def _validate_ai_candidate(
    *,
    interaction: dict[str, Any],
    candidate: dict[str, Any],
    ai_result: dict[str, Any],
) -> tuple[dict[str, Any] | None, list[str]]:
    warnings: list[str] = []
    selector = candidate.get("selector_item") or candidate.get("selector")
    container_selector = candidate.get("selector_contenedor")
    interaction_mode = str(interaction.get("interaction_mode") or "single").lower()
    group_context = _normalize(interaction.get("group_context"))

    if ai_result.get("requires_human_review"):
        return None, ["AI selector_rerank no recomendo autopromocion; mantiene human_review_required=true."]
    if not selector:
        return None, ["AI selector_rerank no devolvio selector_item/selector seleccionado."]
    if candidate.get("selector_origin") != SELECTOR_ORIGIN_RENDERED:
        return None, ["AI selector_rerank rechazado: selector no proviene de DOM renderizado."]

    safety_blockers = selector_safety_blockers(selector, role="item")
    if container_selector:
        safety_blockers.extend(selector_safety_blockers(container_selector, role="contenedor"))
    if safety_blockers:
        return None, ["AI selector_rerank rechazado por safety_blockers: " + "; ".join(safety_blockers)]

    if not candidate.get("exists_in_dom"):
        return None, ["AI selector_rerank rechazado: selector no existe en DOM renderizado."]
    if not candidate.get("closest_runtime_supported") or not candidate.get("click_grounded"):
        return None, ["AI selector_rerank rechazado: selector no queda soportado por closest/click_grounded."]

    match_count = int(candidate.get("match_count") or 0)
    if interaction_mode == "single" and match_count != 1:
        return None, [f"AI selector_rerank rechazado: selector single ambiguo ({match_count} matches)."]
    if interaction_mode == "group" and match_count < 2:
        return None, ["AI selector_rerank rechazado: selector grupal cubre menos de 2 items."]

    expected_variants = _expected_group_variants(interaction)
    if interaction_mode == "group":
        item_limit = group_match_limit(len(expected_variants), candidate.get("candidate_group_item_count"))
        if match_count > item_limit:
            return None, [f"AI selector_rerank rechazado: match_count excesivo ({match_count})."]
        if int(candidate.get("container_match_count") or 0) > container_match_limit():
            return None, [
                "AI selector_rerank rechazado: container_match_count excesivo "
                f"({candidate.get('container_match_count')})."
            ]
        if not useful_visible_text(candidate.get("visible_text")):
            return None, ["AI selector_rerank rechazado: visible_text vacio o sin senales utiles."]

    card_mapping = list(candidate.get("card_mapping") or [])
    card_mapping_complete = _card_mapping_complete_for_ai(interaction, card_mapping)
    if group_context == "card_collection" and not card_mapping_complete:
        return None, ["AI selector_rerank rechazado: card_collection sin card_mapping completo derivado de evidencia."]

    promotion_blockers = [str(item) for item in (candidate.get("promotion_blockers") or [])]
    remaining_blockers = [
        blocker
        for blocker in promotion_blockers
        if not _ai_allowed_to_override_blocker(blocker, has_card_mapping=card_mapping_complete)
    ]
    if remaining_blockers:
        return None, ["AI selector_rerank rechazado por blockers no resolubles: " + "; ".join(remaining_blockers)]

    accepted = dict(candidate)
    accepted["selector_source"] = SELECTOR_SOURCE_AI_RERANK
    accepted["ai_rerank_confidence"] = ai_result.get("confidence")
    accepted["ai_rerank_reason"] = ai_result.get("reason")
    accepted["ai_overridden_blockers"] = [
        blocker for blocker in promotion_blockers if blocker not in remaining_blockers
    ]
    accepted["promotion_blockers"] = []
    accepted["can_promote"] = True
    if group_context == "card_collection" and int(accepted.get("variant_coverage") or 0) <= 0:
        accepted["variant_coverage"] = len(card_mapping)
        accepted["variant_coverage_source"] = "card_mapping"
        accepted["matched_variants"] = list(
            dict.fromkeys(
                [
                    value
                    for mapping in card_mapping
                    for value in (mapping.get("elemento"), mapping.get("tituloCard"))
                    if value
                ]
            )
        )
    return accepted, warnings


def _empty_ai_rerank_artifact(provider: Any | None) -> dict[str, Any]:
    provider_class = provider.__class__.__name__ if provider is not None else "NoopSelectorRerankProvider"
    provider_name = "openai" if provider_class == "OpenAISelectorRerankProvider" else "noop"
    config = getattr(provider, "config", None)
    warnings = [] if provider_name == "openai" else ["AI selector_rerank desactivado; provider=noop."]
    return {
        "attempted": False,
        "provider": provider_name,
        "model": getattr(config, "model_selector", None),
        "interactions": [],
        "selected_count": 0,
        "accepted_count": 0,
        "warnings": warnings,
    }


def propose_selectors(
    measurement_case: dict[str, Any],
    dom_snapshot: dict[str, Any],
    manual_selector_hints: dict[str, Any] | None = None,
    selector_rerank_provider: Any | None = None,
    case_id: str | None = None,
) -> dict[str, Any]:
    state_html = dom_snapshot.get("state_html") or {}
    soups = {state: BeautifulSoup(html, "lxml") for state, html in state_html.items()}
    inventory = [item for item in (dom_snapshot.get("clickable_inventory") or []) if item.get("is_clickable")]
    render_engine = str(dom_snapshot.get("render_engine") or "none")
    ai_rerank_artifact = _empty_ai_rerank_artifact(selector_rerank_provider)

    if not state_html or not inventory:
        selector_evidence = []
        for idx, interaction in enumerate(measurement_case.get("interacciones", []), start=1):
            interaction["selector_candidato"] = None
            interaction["selector_contenedor"] = None
            interaction["selector_item"] = None
            interaction["selector_activador"] = None
            interaction["match_count"] = 0
            interaction.setdefault("warnings", []).append(
                "Sin inventario de clickables observado en DOM; selector en null y human_review_required=true."
            )
            selector_evidence.append(
                {
                    "index": idx,
                    "selector": None,
                    "selector_origin": SELECTOR_ORIGIN_REJECTED,
                    "selector_source": SELECTOR_ORIGIN_REJECTED,
                    "human_review_required": True,
                    "promoted": False,
                    "rejection_reason": "no hay inventario renderizado utilizable",
                    "candidates_considered": 0,
                    "candidates": [],
                }
            )
        return {
            "status": "no_inventory",
            "measurement_case": measurement_case,
            "warnings": ["No hay inventario de clickables del DOM renderizado."],
            "clickable_inventory": inventory,
            "selector_evidence": selector_evidence,
            "selector_summary": _selector_trace_summary(selector_evidence),
            "state_metadata": dom_snapshot.get("state_metadata") or [],
            "manual_selector_hints": manual_selector_hints or {"available": False, "selectors": []},
            "ai_selector_rerank": ai_rerank_artifact,
        }

    selector_evidence: list[dict[str, Any]] = []

    for index, interaction in enumerate(measurement_case.get("interacciones", []), start=1):
        interaction.setdefault("warnings", [])
        interaction_mode = str(interaction.get("interaction_mode") or "single").lower()

        if interaction_mode == "group":
            chosen, traces = _select_group_interaction(
                interaction=interaction,
                inventory=inventory,
                soups=soups,
                dom_snapshot=dom_snapshot,
                manual_selector_hints=manual_selector_hints,
            )
        else:
            chosen, traces = _select_single_interaction(
                interaction=interaction,
                inventory=inventory,
                soups=soups,
                dom_snapshot=dom_snapshot,
            )

        ai_rerank_record: dict[str, Any] | None = None
        can_attempt_ai = (
            interaction_mode == "group"
            and selector_rerank_provider is not None
            and selector_rerank_provider.__class__.__name__ != "NoopSelectorRerankProvider"
            and bool(traces)
            and (not chosen or not chosen.get("can_promote"))
        )
        if can_attempt_ai:
            ai_rerank_artifact["attempted"] = True
            payload = _build_ai_rerank_payload(
                case_id=case_id,
                interaction_index=index,
                interaction=interaction,
                traces=traces,
            )
            ai_rerank_record = {
                "index": index,
                "attempted": True,
                "accepted_after_validation": False,
                "selected": None,
                "rejected": [],
                "reason": None,
                "requires_human_review": True,
                "cache_hit": False,
                "warnings": [],
            }
            try:
                ai_result = selector_rerank_provider.rerank(payload)
                selected_payload = {
                    "selected_selector": ai_result.get("selected_selector"),
                    "selected_container_selector": ai_result.get("selected_container_selector"),
                    "selected_item_selector": ai_result.get("selected_item_selector"),
                    "confidence": ai_result.get("confidence"),
                }
                if not (selected_payload["selected_selector"] or selected_payload["selected_item_selector"]):
                    selected_payload = None
                ai_rerank_record.update(
                    {
                        "provider": ai_result.get("provider"),
                        "model": ai_result.get("model"),
                        "selected": selected_payload,
                        "rejected": ai_result.get("rejects") or [],
                        "reason": ai_result.get("reason"),
                        "requires_human_review": ai_result.get("requires_human_review"),
                        "cache_hit": bool(ai_result.get("cache_hit")),
                        "warnings": list(ai_result.get("warnings") or []),
                    }
                )
                ai_rerank_artifact["provider"] = ai_result.get("provider") or ai_rerank_artifact["provider"]
                ai_rerank_artifact["model"] = ai_result.get("model") or ai_rerank_artifact["model"]
                selected_candidate = _selected_ai_candidate(ai_result, traces)
                if selected_candidate is None and not ai_result.get("requires_human_review"):
                    ai_rerank_record["warnings"].append(
                        "AI selector_rerank eligio un selector que no coincide literalmente con candidatos existentes."
                    )
                if selected_candidate is not None:
                    accepted_candidate, acceptance_warnings = _validate_ai_candidate(
                        interaction=interaction,
                        candidate=selected_candidate,
                        ai_result=ai_result,
                    )
                    ai_rerank_record["warnings"].extend(acceptance_warnings)
                    if accepted_candidate is not None:
                        chosen = accepted_candidate
                        ai_rerank_record["accepted_after_validation"] = True
                        ai_rerank_artifact["accepted_count"] += 1
                if ai_result.get("selected_selector") or ai_result.get("selected_item_selector"):
                    ai_rerank_artifact["selected_count"] += 1
            except Exception as exc:
                ai_rerank_record["warnings"].append(f"AI selector_rerank fallo sin abortar el pipeline: {exc}")
            ai_rerank_artifact["interactions"].append(ai_rerank_record)

        if not chosen:
            interaction["selector_candidato"] = None
            interaction["selector_contenedor"] = None
            interaction["selector_item"] = None
            interaction["selector_activador"] = None
            interaction["match_count"] = 0
            interaction["warnings"].append(
                "No se encontró selector con grounding suficiente para esta interacción; human_review_required=true."
            )
            selector_evidence.append(
                {
                    "index": index,
                    "selector": None,
                    "selector_origin": SELECTOR_ORIGIN_REJECTED,
                    "selector_source": SELECTOR_ORIGIN_REJECTED,
                    "human_review_required": True,
                    "promoted": False,
                    "rejection_reason": "no hay candidatos con existencia en DOM y alineación suficiente",
                    "candidates_considered": len(traces),
                    "candidates": traces[:10],
                    "ai_rerank_attempted": bool(ai_rerank_record),
                    "ai_rerank_selected": bool((ai_rerank_record or {}).get("selected")),
                    "ai_rerank_reason": (ai_rerank_record or {}).get("reason"),
                    "ai_rerank_requires_human_review": (ai_rerank_record or {}).get("requires_human_review", True),
                }
            )
            if interaction_mode == "group":
                interaction["warnings"].append(
                    "No se encontro selector grupal seguro variant-first; se rechazan selectores genericos, contenedores no discriminantes, variant_coverage insuficiente o match_count excesivo; human_review_required=true."
                )
            continue

        promoted = bool(chosen.get("can_promote"))
        interaction["match_count"] = int(chosen.get("match_count") or 0)
        if promoted:
            selector = str(chosen["selector"])
            interaction["selector_candidato"] = selector
            interaction["selector_contenedor"] = chosen.get("selector_contenedor")
            interaction["selector_item"] = chosen.get("selector_item") or selector
            interaction["selector_activador"] = f"{selector}, {selector} *"
            if chosen.get("selector_source") in {MANUAL_GOLDEN_HINT_SOURCE, SELECTOR_SOURCE_AI_RERANK}:
                interaction["selector_metadata"] = {
                    "selector_source": chosen.get("selector_source"),
                    "hint_file": chosen.get("hint_file"),
                    "card_mapping": chosen.get("card_mapping") or [],
                }
                if chosen.get("ai_rerank_reason"):
                    interaction["selector_metadata"]["ai_rerank_reason"] = chosen.get("ai_rerank_reason")
        else:
            interaction["selector_candidato"] = None
            interaction["selector_contenedor"] = None
            interaction["selector_item"] = None
            interaction["selector_activador"] = None
            interaction.pop("selector_metadata", None)

        if chosen["selector_origin"] == SELECTOR_ORIGIN_FALLBACK:
            interaction["warnings"].append(
                "Selector observado solo en raw_html_fallback: no se autopromueve y requiere revisión humana."
            )
        if not chosen.get("has_minimum_alignment", True) and interaction_mode != "group":
            interaction["warnings"].append(
                "La evidencia textual/atributiva del nodo es insuficiente para autopromover selector."
            )
        if chosen.get("promotion_blockers"):
            interaction["warnings"].append(
                "Selector retenido por seguridad: " + "; ".join(chosen["promotion_blockers"])
            )
        if interaction_mode == "group" and promoted:
            interaction["warnings"].append(
                f"Interacción grupal modelada con selector_contenedor={chosen.get('selector_contenedor')} y selector_item={chosen.get('selector_item')}."
            )

        final_selector_source = SELECTOR_ORIGIN_REJECTED
        if promoted:
            if chosen.get("selector_source") in {MANUAL_GOLDEN_HINT_SOURCE, SELECTOR_SOURCE_AI_RERANK}:
                final_selector_source = chosen.get("selector_source")
            else:
                final_selector_source = SELECTOR_SOURCE_DETERMINISTIC

        selector_evidence.append(
            {
                "index": index,
                "selector": chosen.get("selector") if promoted else None,
                "selector_origin": chosen.get("selector_origin") or SELECTOR_ORIGIN_REJECTED,
                "selector_source": final_selector_source,
                "hint_file": chosen.get("hint_file"),
                "human_review_required": (not promoted) or (
                    interaction_mode == "single" and chosen.get("match_count") != 1
                ),
                "promoted": promoted,
                "rejection_reason": None if promoted else "; ".join(chosen.get("promotion_blockers") or []),
                "chosen": chosen,
                "candidates_considered": len(traces),
                "candidates": traces[:10],
                "ai_rerank_attempted": bool(ai_rerank_record),
                "ai_rerank_selected": bool((ai_rerank_record or {}).get("selected")),
                "ai_rerank_reason": (ai_rerank_record or {}).get("reason"),
                "ai_rerank_requires_human_review": (ai_rerank_record or {}).get("requires_human_review", True),
            }
        )

    warnings: list[str] = []
    if render_engine == "raw_html_fallback":
        warnings.append("DOM renderizado no disponible: cualquier candidato de raw_html_fallback queda degradado.")

    return {
        "status": "ok",
        "measurement_case": measurement_case,
        "warnings": warnings,
        "clickable_inventory": inventory,
        "selector_evidence": selector_evidence,
        "selector_summary": _selector_trace_summary(selector_evidence),
        "state_metadata": dom_snapshot.get("state_metadata") or [],
        "manual_selector_hints": manual_selector_hints or {"available": False, "selectors": []},
        "ai_selector_rerank": ai_rerank_artifact,
    }
