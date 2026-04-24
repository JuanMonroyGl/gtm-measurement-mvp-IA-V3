"""GTM tag template generation with human-readable closest branches."""

from __future__ import annotations

import json
import re
from typing import Any

from core.processing.selectors.safety import is_unsafe_group_selector


FORBIDDEN_ABSTRACT_HELPERS = (
    "resolveGroupNode",
    "resolveGroupValue",
    "matchKnownVariant",
    "collectContextRoots",
)


def _to_js(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _selector_literal(selector: str) -> str:
    parts = [part.strip() for part in selector.split(",") if part.strip()]
    if len(parts) <= 1:
        return _to_js(selector)
    return " +\n        ".join(_to_js(f"{part}{', ' if index < len(parts) - 1 else ''}") for index, part in enumerate(parts))


def _extract_selector_ids(selector: str | None) -> list[str]:
    if not selector:
        return []
    ids: list[str] = []
    for match in re.finditer(r"#([A-Za-z_][\w-]*)", selector):
        value = match.group(1)
        if value not in ids:
            ids.append(value)
    return ids


def _is_card_interaction(interaction: dict[str, Any]) -> bool:
    return "card" in str(interaction.get("tipo_evento") or "").lower() or (
        str(interaction.get("group_context") or "").lower() == "card_collection"
    )


def _build_selector_rules(measurement_case: dict[str, Any]) -> list[dict[str, Any]]:
    rules: list[dict[str, Any]] = []
    for index, interaction in enumerate(measurement_case.get("interacciones", []), start=1):
        selector = interaction.get("selector_item") or interaction.get("selector_candidato")
        if not selector:
            continue
        selector_text = str(selector).strip()
        if not selector_text or is_unsafe_group_selector(selector_text):
            continue
        container_selector = interaction.get("selector_contenedor")
        rules.append(
            {
                "index": index,
                "selector": selector_text,
                "container_selector": str(container_selector).strip() if container_selector else None,
                "event_name": str(interaction.get("tipo_evento") or "Clic Boton"),
                "flujo": str(interaction.get("flujo") or ""),
                "ubicacion": str(interaction.get("ubicacion") or ""),
                "is_card": _is_card_interaction(interaction),
                "element_variants": [str(item) for item in (interaction.get("element_variants") or [])],
                "title_variants": [str(item) for item in (interaction.get("title_variants") or [])],
                "card_mapping": list((interaction.get("selector_metadata") or {}).get("card_mapping") or []),
            }
        )
    return rules


def _assert_no_conflicting_duplicate_selectors(selector_rules: list[dict[str, Any]]) -> None:
    grouped: dict[str, set[tuple[str, str, str]]] = {}
    for rule in selector_rules:
        grouped.setdefault(rule["selector"], set()).add((rule["event_name"], rule["flujo"], rule["ubicacion"]))

    conflicts = {selector: payloads for selector, payloads in grouped.items() if len(payloads) > 1}
    if not conflicts:
        return

    details = []
    for selector, payloads in conflicts.items():
        payload_list = ", ".join(f"{event}/{flujo}/{ubicacion}" for event, flujo, ubicacion in sorted(payloads))
        details.append(f"{selector} -> [{payload_list}]")
    raise ValueError(
        "Conflicto de selectores en generacion de tag: multiples interacciones comparten el mismo closest "
        f"con payload distinto. Detalles: {'; '.join(details)}"
    )


def _append_value_from_item(lines: list[str], indent: str = "      ") -> None:
    lines.extend(
        [
            f"{indent}var value = cText;",
            f"{indent}if (typeof value === 'function') {{ value = value(item); }}",
            f"{indent}if (!value) {{",
            f"{indent}  value = (typeof getText === 'function') ? getText(item) : getText;",
            f"{indent}}}",
            f"{indent}if (!value && item) {{ value = item.innerText || item.textContent; }}",
            f"{indent}value = (typeof clean === 'function') ? clean(value || '') : (value || '');",
        ]
    )


def _append_card_title_resolution(lines: list[str], rule: dict[str, Any]) -> None:
    selector_ids = _extract_selector_ids(rule.get("selector"))
    container_ids = _extract_selector_ids(rule.get("container_selector"))
    card_ids = selector_ids or container_ids
    element_variants = rule.get("element_variants") or []
    title_variants = rule.get("title_variants") or []
    card_mapping = [
        item
        for item in (rule.get("card_mapping") or [])
        if item.get("card_id") and (item.get("elemento") or item.get("tituloCard"))
    ]
    if card_mapping:
        lines.extend(
            [
                "      // Fallback plan-based: IDs observados en DOM y titulos tomados del plan de medicion.",
                "      var card = item.closest(" + _to_js(", ".join(f"#{item['card_id']}" for item in card_mapping)) + ");",
                "      var cardsData = {",
            ]
        )
        for index, item in enumerate(card_mapping):
            comma = "," if index < len(card_mapping) - 1 else ""
            lines.extend(
                [
                    f"        {_to_js(item['card_id'])}: {{",
                    f"          elemento: {_to_js(item.get('elemento') or '')},",
                    f"          tituloCard: {_to_js(item.get('tituloCard') or '')}",
                    f"        }}{comma}",
                ]
            )
        lines.extend(
            [
                "      };",
                "      var cardInfo = card ? cardsData[card.id] : null;",
                "      if (cardInfo && cardInfo.elemento) { value = cardInfo.elemento; }",
                "      if (cardInfo && cardInfo.tituloCard) { data['tituloCard'] = cardInfo.tituloCard; }",
            ]
        )
        return
    if card_ids and title_variants:
        mapping_count = min(len(card_ids), len(title_variants))
        lines.extend(
            [
                "      // Fallback plan-based: IDs observados en DOM y titulos tomados del plan de medicion.",
                "      var card = item.closest(" + _to_js(", ".join(f"#{card_id}" for card_id in card_ids[:mapping_count])) + ");",
                "      var cardsData = {",
            ]
        )
        for index, card_id in enumerate(card_ids[:mapping_count]):
            elemento = element_variants[index] if index < len(element_variants) else ""
            title = title_variants[index]
            comma = "," if index < mapping_count - 1 else ""
            lines.extend(
                [
                    f"        {_to_js(card_id)}: {{",
                    f"          elemento: {_to_js(elemento)},",
                    f"          tituloCard: {_to_js(title)}",
                    f"        }}{comma}",
                ]
            )
        lines.extend(
            [
                "      };",
                "      var cardInfo = card ? cardsData[card.id] : null;",
                "      if (cardInfo && cardInfo.elemento) { value = cardInfo.elemento; }",
                "      if (cardInfo && cardInfo.tituloCard) { data['tituloCard'] = cardInfo.tituloCard; }",
            ]
        )
        return

    container_selector = rule.get("container_selector")
    if container_selector and not is_unsafe_group_selector(container_selector):
        lines.append(f"      var card = item.closest({_to_js(container_selector)});")
    else:
        lines.append("      var card = item.closest('[id], article, section, li, .card, .swiper-slide');")
    lines.extend(
        [
            "      var titleNode = card ? card.querySelector('[data-card-title], .card-title, .titulo, h2, h3, h4, strong') : null;",
            "      var tituloCard = titleNode ? (titleNode.innerText || titleNode.textContent) : '';",
            "      tituloCard = (typeof clean === 'function') ? clean(tituloCard || '') : (tituloCard || '');",
            "      if (tituloCard) { data['tituloCard'] = tituloCard; }",
        ]
    )


def build_tag_template(measurement_case: dict[str, Any]) -> str:
    activo = str(measurement_case.get("activo") or "bancolombia")
    seccion = str(measurement_case.get("seccion") or "pagos")
    selector_rules = _build_selector_rules(measurement_case)
    _assert_no_conflicting_duplicate_selectors(selector_rules)

    lines = [
        "<script>",
        "  var element = {{Click Element}};",
        "  var getClean = {{JS - Function - Format LowerCase}};",
        "  var getClickText = {{JS - Click Text - Btn and A}};",
        "  var getTextClose = {{JS - Function - Get Text Close}};",
        "",
        f"  var eventData = {{ activo: {_to_js(activo)}, seccion: {_to_js(seccion)} }}",
        "",
        "  function setDataEvent(data, e, cText, clean, getText) {",
    ]

    for idx, rule in enumerate(selector_rules):
        prefix = "if" if idx == 0 else "else if"
        lines.extend(
            [
                f"    {prefix}(e.closest({_selector_literal(rule['selector'])})) {{",
                f"      var item = e.closest({_selector_literal(rule['selector'])});",
            ]
        )
        _append_value_from_item(lines)
        if rule["is_card"]:
            _append_card_title_resolution(lines, rule)
        else:
            lines.append("      if (data['tituloCard']) { delete data['tituloCard']; }")
        lines.extend(
            [
                "      data['elemento'] = value;",
                f"      data['flujo'] = {_to_js(rule['flujo'])};",
                f"      data['ubicacion'] = {_to_js(rule['ubicacion'])};",
                "",
                f"      if (document.location.href.search('appspot.com') == -1) {{analytics.track({_to_js(rule['event_name'])}, data)}};",
                "      return;",
                "    }",
            ]
        )

    if not selector_rules:
        lines.append("    // No interaction rules available for this case.")

    lines.extend(
        [
            "  }",
            "",
            "  setDataEvent(eventData, element, getClickText, getClean, getTextClose);",
            "</script>",
            "",
        ]
    )
    return "\n".join(lines)


def summarize_generated_rules(measurement_case: dict[str, Any], tag_template: str | None = None) -> dict[str, Any]:
    rules = _build_selector_rules(measurement_case)
    total = len(measurement_case.get("interacciones", []))
    generated = len(rules)
    tag_text = tag_template or build_tag_template(measurement_case)
    forbidden_helpers = [helper for helper in FORBIDDEN_ABSTRACT_HELPERS if helper in tag_text]
    return {
        "total_interactions": total,
        "generated_rules": generated,
        "generated_rule_coverage": round(generated / total, 4) if total else 0.0,
        "covered_interaction_indexes": [rule["index"] for rule in rules],
        "covered_events": [rule["event_name"] for rule in rules],
        "forbidden_helpers": forbidden_helpers,
        "uses_json_rule_blob": "var groupRule = {" in tag_text or '"element_variants":' in tag_text,
        "uses_resolve_group_node": "resolveGroupNode" in tag_text,
    }
