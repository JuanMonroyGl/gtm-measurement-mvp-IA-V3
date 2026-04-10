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


EVENT_BY_SELECTOR = {
    'a[href*="apps.apple.com"]': "Clic Boton",
    '.card-razon-beneficio-vivienda .contenido-card-razon-beneficio-vivienda': "Clic Card",
    '.contenedor-buttons-tabs .swiper .swiper-wrapper .swiper-slide': "Clic Boton",
    '.contenido-preguntas-frecuentes .acordeon-pregunta-frecuente': "Clic Tap",
    'a[href*=".pdf"]': "Clic Link",
}


def _escape_js(value: str | None) -> str:
    return (value or "").replace("\\", "\\\\").replace('"', '\\"')


def _interaction_map(measurement_case: dict[str, Any]) -> dict[str, dict[str, Any]]:
    mapping: dict[str, dict[str, Any]] = {}
    for interaction in measurement_case.get("interacciones", []):
        selector = interaction.get("selector_candidato")
        if selector in SELECTOR_ORDER:
            mapping[selector] = interaction
    return mapping


def build_tag_template(measurement_case: dict[str, Any]) -> str:
    interactions_by_selector = _interaction_map(measurement_case)
    activo = _escape_js(measurement_case.get("activo") or "bancolombia")
    seccion = _escape_js(measurement_case.get("seccion") or "pagos")

    lines: list[str] = [
        "<script>",
        "(function() {",
        "  var element = {{Click Element}};",
        "  if (!element) return;",
        "  var getClean = {{JS - Function - Format LowerCase}};",
        "  var getClickText = {{JS - Click Text - Btn and A}};",
        "  var getTextClose = {{JS - Function - Get Text Close}};",
        f"  var eventData = {{ activo: \"{activo}\", seccion: \"{seccion}\" }};",
        "  function setDataEvent(data, e, cText, clean, getText) {",
        "    data['elemento'] = cText || clean(getText(e) || getTextClose(e) || '');",
        "    return data;",
        "  }",
        "  var e = element;",
        "  var cText = getClean(getClickText(e) || getTextClose(e) || '');",
    ]

    branch_started = False
    for selector in SELECTOR_ORDER:
        interaction = interactions_by_selector.get(selector)
        if not interaction:
            continue

        prefix = "if" if not branch_started else "else if"
        branch_started = True

        flujo = _escape_js(interaction.get("flujo"))
        ubicacion = _escape_js(interaction.get("ubicacion"))
        evento = EVENT_BY_SELECTOR[selector]

        lines.extend(
            [
                f"  {prefix} (e.closest('{selector}')) {{",
                "    var data = Object.assign({}, eventData);",
                f"    data['flujo'] = \"{flujo}\";",
                f"    data['ubicacion'] = \"{ubicacion}\";",
                "    data = setDataEvent(data, e, cText, getClean, getClickText);",
                f"    if (document.location.href.search('appspot.com') == -1) {{analytics.track('{evento}', data)}};",
                "    return;",
                "  }",
            ]
        )

    lines.extend(["})();", "</script>", ""])
    return "\n".join(lines)
