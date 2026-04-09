"""GTM tag template generation."""

from __future__ import annotations

from typing import Any


SELECTOR_ORDER = [
    'a[href*="apps.apple.com"]',
    '.card-razon-beneficio-vivienda .contenido-card-razon-beneficio-vivienda',
    '.contenedor-buttons-tabs .swiper .swiper-wrapper .swiper-slide',
    '.contenido-preguntas-frecuentes .acordeon-pregunta-frecuente',
    'a[href*=".pdf"]',
]


def _escape_js(value: str | None) -> str:
    return (value or "").replace("\\", "\\\\").replace('"', '\\"')


def _interaction_map(measurement_case: dict[str, Any]) -> dict[str, dict[str, Any]]:
    mapping: dict[str, dict[str, Any]] = {}
    for interaction in measurement_case.get("interacciones", []):
        selector = interaction.get("selector_candidato")
        if not selector:
            continue
        mapping[selector] = interaction
    return mapping


def build_tag_template(measurement_case: dict[str, Any]) -> str:
    """Build one functional GTM tag script with if/else-if by interaction."""
    case_activo = _escape_js(measurement_case.get("activo"))
    case_seccion = _escape_js(measurement_case.get("seccion"))

    interactions_by_selector = _interaction_map(measurement_case)

    branch_lines: list[str] = []
    for idx, selector in enumerate(SELECTOR_ORDER):
        interaction = interactions_by_selector.get(selector)
        if not interaction:
            continue

        keyword = "if" if not branch_lines else "else if"
        tipo_evento = _escape_js(interaction.get("tipo_evento"))
        flujo = _escape_js(interaction.get("flujo"))
        ubicacion = _escape_js(interaction.get("ubicacion"))

        branch_lines.extend(
            [
                f"  {keyword} (element.closest('{selector}')) {{",
                f"    analytics.track(\"{tipo_evento}\", {{",
                f"      activo: \"{case_activo}\",",
                f"      seccion: \"{case_seccion}\",",
                f"      flujo: \"{flujo}\",",
                f"      ubicacion: \"{ubicacion}\",",
                "      elemento: cText",
                "    });",
                "  }",
            ]
        )

    if not branch_lines:
        branch_lines = ["  return;"]

    lines = [
        "<script>",
        "(function() {",
        "  var element = {{Click Element}};",
        "  if (!element) return;",
        "  var getClean = {{JS - Function - Format LowerCase}};",
        "  var getClickText = {{JS - Click Text - Btn and A}};",
        "  var getTextClose = {{JS - Function - Get Text Close}};",
        "  var cText = getClean(getClickText(element) || getTextClose(element) || '');",
    ]
    lines.extend(branch_lines)
    lines.extend(["})();", "</script>", ""])
    return "\n".join(lines)
