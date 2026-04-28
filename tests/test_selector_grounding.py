import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.checks.output_gate import evaluate_output_gate
from core.output_generation.generate_gtm_tag import build_tag_template
from core.output_generation.generate_trigger import build_consolidated_trigger_selector
from core.processing.selectors.build_selectors import propose_selectors
from core.processing.selectors.validate_selectors import validate_selector_candidates


class SelectorGroundingTests(unittest.TestCase):
    def test_selector_from_observed_inventory_only(self) -> None:
        measurement_case = {
            "interacciones": [
                {
                    "tipo_evento": "Clic Boton",
                    "flujo": "home",
                    "elemento": "pagar",
                    "ubicacion": "hero",
                    "texto_referencia": "Pagar ahora",
                    "selector_candidato": None,
                    "selector_activador": None,
                    "match_count": None,
                    "warnings": [],
                }
            ]
        }
        dom_snapshot = {
            "render_engine": "playwright_multi_state",
            "state_html": {
                "initial_render": '<html><body><button id="pay-btn" data-gtm-mvp-node-id="node-1">Pagar ahora</button></body></html>'
            },
            "clickable_inventory": [
                {
                    "node_id": "node-1",
                    "tag": "button",
                    "text": "Pagar ahora",
                    "context_text": "Hero principal",
                    "aria_label": None,
                    "title": None,
                    "href": None,
                    "id": "pay-btn",
                    "class_list": [],
                    "ancestors": [],
                    "outer_html_excerpt": '<button id="pay-btn">Pagar ahora</button>',
                    "bounding_box": None,
                    "state": "initial_render",
                    "source": "observed_rendered_dom",
                    "is_visible": True,
                    "is_clickable": True,
                    "selector_candidates": ["#pay-btn", "button"],
                }
            ],
        }

        build = propose_selectors(measurement_case, dom_snapshot)
        validate_selector_candidates(measurement_case, dom_snapshot, build.get("selector_evidence"))

        self.assertEqual(measurement_case["interacciones"][0]["selector_candidato"], "#pay-btn")

    def test_selector_null_when_not_observed(self) -> None:
        measurement_case = {
            "interacciones": [
                {
                    "tipo_evento": "Clic Boton",
                    "flujo": "home",
                    "elemento": "inexistente",
                    "ubicacion": "hero",
                    "texto_referencia": "No existe",
                    "selector_candidato": None,
                    "selector_activador": None,
                    "match_count": None,
                    "warnings": [],
                }
            ]
        }
        dom_snapshot = {
            "render_engine": "playwright_multi_state",
            "state_html": {
                "initial_render": '<html><body><button id="pay-btn" data-gtm-mvp-node-id="node-1">Pagar ahora</button></body></html>'
            },
            "clickable_inventory": [],
        }

        build = propose_selectors(measurement_case, dom_snapshot)
        validate_selector_candidates(measurement_case, dom_snapshot, build.get("selector_evidence"))

        self.assertIsNone(measurement_case["interacciones"][0]["selector_candidato"])
        self.assertEqual(measurement_case["interacciones"][0]["match_count"], 0)
        self.assertTrue(any("human_review_required" in warning for warning in measurement_case["interacciones"][0]["warnings"]))

    def test_derived_id_class_selector_is_registered_for_gate(self) -> None:
        measurement_case = {
            "activo": "bancolombia",
            "seccion": "personas",
            "interacciones": [
                {
                    "tipo_evento": "Clic Boton",
                    "flujo": "mastercard",
                    "elemento": "{{solicitala ahora}}",
                    "element_variants": ["solicitala ahora"],
                    "ubicacion": "mastercard joven",
                    "texto_referencia": "¡SOLICÍTALA AHORA!",
                    "selector_candidato": None,
                    "selector_activador": None,
                    "match_count": None,
                    "warnings": [],
                }
            ],
        }
        dom_snapshot = {
            "render_engine": "playwright_multi_state",
            "state_html": {
                "initial_render": (
                    '<html><body>'
                    '<a id="master-solicita-tarjeta-0" class="btn button-primary" '
                    'data-gtm-mvp-node-id="node-1">¡SOLICÍTALA AHORA!</a>'
                    '<a id="master-solicita-tarjeta-0" class="btn-secundario-small" '
                    'data-gtm-mvp-node-id="node-2">¡SOLICÍTALA!</a>'
                    "</body></html>"
                )
            },
            "clickable_inventory": [
                {
                    "node_id": "node-1",
                    "tag": "a",
                    "text": "¡SOLICÍTALA AHORA!",
                    "context_text": "Mastercard Joven",
                    "aria_label": None,
                    "title": None,
                    "href": None,
                    "id": "master-solicita-tarjeta-0",
                    "class_list": ["btn", "button-primary"],
                    "ancestors": [],
                    "outer_html_excerpt": '<a id="master-solicita-tarjeta-0" class="btn button-primary">¡SOLICÍTALA AHORA!</a>',
                    "bounding_box": None,
                    "state": "initial_render",
                    "source": "observed_rendered_dom",
                    "is_visible": True,
                    "is_clickable": False,
                    "selector_candidates": ["#master-solicita-tarjeta-0", "a.btn.button-primary", "a"],
                },
                {
                    "node_id": "node-2",
                    "tag": "a",
                    "text": "¡SOLICÍTALA!",
                    "context_text": "Mastercard Joven",
                    "aria_label": None,
                    "title": None,
                    "href": None,
                    "id": "master-solicita-tarjeta-0",
                    "class_list": ["btn-secundario-small"],
                    "ancestors": [],
                    "outer_html_excerpt": '<a id="master-solicita-tarjeta-0" class="btn-secundario-small">¡SOLICÍTALA!</a>',
                    "bounding_box": None,
                    "state": "initial_render",
                    "source": "observed_rendered_dom",
                    "is_visible": True,
                    "is_clickable": False,
                    "selector_candidates": ["#master-solicita-tarjeta-0", "a.btn-secundario-small", "a"],
                },
            ],
        }

        build = propose_selectors(measurement_case, dom_snapshot)
        validate_selector_candidates(measurement_case, dom_snapshot, build.get("selector_evidence"))

        selector = measurement_case["interacciones"][0]["selector_candidato"]
        self.assertEqual(selector, "#master-solicita-tarjeta-0.button-primary")
        self.assertIn(selector, dom_snapshot["clickable_inventory"][0]["selector_candidates"])

        tag_template = build_tag_template(measurement_case)
        trigger_selector = build_consolidated_trigger_selector(measurement_case)
        gate = evaluate_output_gate(
            measurement_case=measurement_case,
            selector_trace={"selector_evidence": build["selector_evidence"]},
            clickable_inventory={"items": dom_snapshot["clickable_inventory"]},
            tag_template=tag_template,
            trigger_selector=trigger_selector,
        )

        self.assertTrue(gate["passed"], gate["errors"])

    def test_duplicate_composite_group_selectors_do_not_crash(self) -> None:
        measurement_case = {
            "interacciones": [
                {
                    "tipo_evento": "Clic Link",
                    "interaction_mode": "group",
                    "group_context": "card_collection",
                    "element_variants": ["Cuenta AFC", "Crédito Hipotecario"],
                    "title_variants": ["Quiero una casa"],
                    "flujo": "productos",
                    "ubicacion": "tab del medio",
                    "selector_candidato": None,
                    "selector_activador": None,
                    "match_count": None,
                    "warnings": [],
                }
            ],
        }
        dom_snapshot = {
            "render_engine": "playwright_multi_state",
            "state_html": {
                "initial_render": (
                    '<html><body><section id="productos"><div class="card">'
                    "<h6>Quiero una casa</h6>"
                    '<a class="productos-ElementoLink" data-gtm-mvp-node-id="node-1">Cuenta AFC</a>'
                    '<a class="productos-ElementoLink" data-gtm-mvp-node-id="node-2">Crédito Hipotecario</a>'
                    "</div></section></body></html>"
                )
            },
            "clickable_inventory": [
                {
                    "node_id": "node-1",
                    "tag": "a",
                    "text": "Cuenta AFC",
                    "context_text": "Quiero una casa Cuenta AFC Crédito Hipotecario",
                    "aria_label": None,
                    "title": None,
                    "href": None,
                    "id": None,
                    "class_list": ["productos-ElementoLink"],
                    "ancestors": [
                        {"tag": "div", "id": None, "classes": ["card"]},
                        {"tag": "section", "id": "productos", "classes": []},
                    ],
                    "outer_html_excerpt": '<a class="productos-ElementoLink">Cuenta AFC</a>',
                    "bounding_box": None,
                    "state": "initial_render",
                    "source": "observed_rendered_dom",
                    "is_visible": True,
                    "is_clickable": False,
                    "selector_candidates": ["a.productos-ElementoLink", "a"],
                },
                {
                    "node_id": "node-2",
                    "tag": "a",
                    "text": "Crédito Hipotecario",
                    "context_text": "Quiero una casa Cuenta AFC Crédito Hipotecario",
                    "aria_label": None,
                    "title": None,
                    "href": None,
                    "id": None,
                    "class_list": ["productos-ElementoLink"],
                    "ancestors": [
                        {"tag": "div", "id": None, "classes": ["card"]},
                        {"tag": "section", "id": "productos", "classes": []},
                    ],
                    "outer_html_excerpt": '<a class="productos-ElementoLink">Crédito Hipotecario</a>',
                    "bounding_box": None,
                    "state": "initial_render",
                    "source": "observed_rendered_dom",
                    "is_visible": True,
                    "is_clickable": False,
                    "selector_candidates": ["a.productos-ElementoLink", "a"],
                },
            ],
        }

        build = propose_selectors(measurement_case, dom_snapshot)

        self.assertEqual(build["status"], "ok")
        self.assertGreater(build["selector_evidence"][0]["candidates_considered"], 0)

    def test_clic_link_card_collection_can_use_link_family_without_title_match(self) -> None:
        measurement_case = {
            "interacciones": [
                {
                    "tipo_evento": "Clic Link",
                    "interaction_mode": "group",
                    "group_context": "card_collection",
                    "element_variants": ["Cuenta AFC", "Crédito Hipotecario"],
                    "title_variants": ["Quiero una casa"],
                    "flujo": "productos",
                    "ubicacion": "tab del medio",
                    "selector_candidato": None,
                    "selector_activador": None,
                    "match_count": None,
                    "warnings": [],
                }
            ],
        }
        dom_snapshot = {
            "render_engine": "playwright_multi_state",
            "state_html": {
                "initial_render": (
                    '<html><body><div class="productos-contenidoItems">'
                    '<a class="productos-ElementoLink" data-gtm-mvp-node-id="node-1">Cuenta AFC</a>'
                    '<a class="productos-ElementoLink" data-gtm-mvp-node-id="node-2">Crédito Hipotecario</a>'
                    "</div></body></html>"
                )
            },
            "clickable_inventory": [
                {
                    "node_id": "node-1",
                    "tag": "a",
                    "text": "Cuenta AFC",
                    "context_text": "Cuenta AFC Crédito Hipotecario",
                    "aria_label": None,
                    "title": None,
                    "href": None,
                    "id": None,
                    "class_list": ["productos-ElementoLink"],
                    "ancestors": [{"tag": "div", "id": None, "classes": ["productos-contenidoItems"]}],
                    "outer_html_excerpt": '<a class="productos-ElementoLink">Cuenta AFC</a>',
                    "bounding_box": None,
                    "state": "initial_render",
                    "source": "observed_rendered_dom",
                    "is_visible": True,
                    "is_clickable": False,
                    "selector_candidates": ["a.productos-ElementoLink", "a"],
                },
                {
                    "node_id": "node-2",
                    "tag": "a",
                    "text": "Crédito Hipotecario",
                    "context_text": "Cuenta AFC Crédito Hipotecario",
                    "aria_label": None,
                    "title": None,
                    "href": None,
                    "id": None,
                    "class_list": ["productos-ElementoLink"],
                    "ancestors": [{"tag": "div", "id": None, "classes": ["productos-contenidoItems"]}],
                    "outer_html_excerpt": '<a class="productos-ElementoLink">Crédito Hipotecario</a>',
                    "bounding_box": None,
                    "state": "initial_render",
                    "source": "observed_rendered_dom",
                    "is_visible": True,
                    "is_clickable": False,
                    "selector_candidates": ["a.productos-ElementoLink", "a"],
                },
            ],
        }

        build = propose_selectors(measurement_case, dom_snapshot)

        evidence = build["selector_evidence"][0]
        self.assertTrue(evidence["promoted"], evidence.get("rejection_reason"))
        self.assertEqual(measurement_case["interacciones"][0]["selector_candidato"], "div.productos-contenidoItems a.productos-ElementoLink")

    def test_group_prefers_repeated_dom_family_over_mixed_composite(self) -> None:
        measurement_case = {
            "interacciones": [
                {
                    "tipo_evento": "Clic Menu",
                    "interaction_mode": "group",
                    "group_context": "top_navigation",
                    "element_variants": ["Tarjetas de crédito", "Cuentas", "Inversiones"],
                    "flujo": "digital",
                    "ubicacion": "inicio arriba",
                    "selector_candidato": None,
                    "selector_activador": None,
                    "match_count": None,
                    "warnings": [],
                }
            ],
        }
        dom_snapshot = {
            "render_engine": "playwright_multi_state",
            "state_html": {
                "initial_render": (
                    '<html><body><section id="menu-solicitud-productos"><ul class="centra-items-hor">'
                    '<li><a id="filtro-tarjetas" class="productos-filtro_categoria active" '
                    'data-gtm-mvp-node-id="node-1">Tarjetas de crédito</a></li>'
                    '<li><a id="filtro-cuentas" class="productos-filtro_categoria" '
                    'data-gtm-mvp-node-id="node-2">Cuentas</a></li>'
                    '<li><a id="filtro-inversiones" class="productos-filtro_categoria" '
                    'data-gtm-mvp-node-id="node-3">Inversiones</a></li>'
                    "</ul></section>"
                    '<div class="productos-contenidoItems"><a class="productos-ElementoLink" '
                    'data-gtm-mvp-node-id="node-4">Tarjetas de crédito</a></div>'
                    "</body></html>"
                )
            },
            "clickable_inventory": [
                {
                    "node_id": "node-1",
                    "tag": "a",
                    "text": "Tarjetas de crédito",
                    "context_text": "Tarjetas de crédito Cuentas Inversiones",
                    "aria_label": None,
                    "title": None,
                    "href": None,
                    "id": "filtro-tarjetas",
                    "class_list": ["productos-filtro_categoria", "active"],
                    "ancestors": [
                        {"tag": "li", "id": None, "classes": []},
                        {"tag": "ul", "id": None, "classes": ["centra-items-hor"]},
                        {"tag": "section", "id": "menu-solicitud-productos", "classes": []},
                    ],
                    "outer_html_excerpt": '<a id="filtro-tarjetas" class="productos-filtro_categoria active">Tarjetas de crédito</a>',
                    "bounding_box": None,
                    "state": "initial_render",
                    "source": "observed_rendered_dom",
                    "is_visible": True,
                    "is_clickable": False,
                    "selector_candidates": ["#filtro-tarjetas", "a.productos-filtro_categoria.active", "a"],
                },
                {
                    "node_id": "node-2",
                    "tag": "a",
                    "text": "Cuentas",
                    "context_text": "Tarjetas de crédito Cuentas Inversiones",
                    "aria_label": None,
                    "title": None,
                    "href": None,
                    "id": "filtro-cuentas",
                    "class_list": ["productos-filtro_categoria"],
                    "ancestors": [
                        {"tag": "li", "id": None, "classes": []},
                        {"tag": "ul", "id": None, "classes": ["centra-items-hor"]},
                        {"tag": "section", "id": "menu-solicitud-productos", "classes": []},
                    ],
                    "outer_html_excerpt": '<a id="filtro-cuentas" class="productos-filtro_categoria">Cuentas</a>',
                    "bounding_box": None,
                    "state": "initial_render",
                    "source": "observed_rendered_dom",
                    "is_visible": True,
                    "is_clickable": False,
                    "selector_candidates": ["#filtro-cuentas", "a.productos-filtro_categoria", "a"],
                },
                {
                    "node_id": "node-3",
                    "tag": "a",
                    "text": "Inversiones",
                    "context_text": "Tarjetas de crédito Cuentas Inversiones",
                    "aria_label": None,
                    "title": None,
                    "href": None,
                    "id": "filtro-inversiones",
                    "class_list": ["productos-filtro_categoria"],
                    "ancestors": [
                        {"tag": "li", "id": None, "classes": []},
                        {"tag": "ul", "id": None, "classes": ["centra-items-hor"]},
                        {"tag": "section", "id": "menu-solicitud-productos", "classes": []},
                    ],
                    "outer_html_excerpt": '<a id="filtro-inversiones" class="productos-filtro_categoria">Inversiones</a>',
                    "bounding_box": None,
                    "state": "initial_render",
                    "source": "observed_rendered_dom",
                    "is_visible": True,
                    "is_clickable": False,
                    "selector_candidates": ["#filtro-inversiones", "a.productos-filtro_categoria", "a"],
                },
                {
                    "node_id": "node-4",
                    "tag": "a",
                    "text": "Tarjetas de crédito",
                    "context_text": "Tarjetas de crédito",
                    "aria_label": None,
                    "title": None,
                    "href": None,
                    "id": None,
                    "class_list": ["productos-ElementoLink"],
                    "ancestors": [{"tag": "div", "id": None, "classes": ["productos-contenidoItems"]}],
                    "outer_html_excerpt": '<a class="productos-ElementoLink">Tarjetas de crédito</a>',
                    "bounding_box": None,
                    "state": "initial_render",
                    "source": "observed_rendered_dom",
                    "is_visible": True,
                    "is_clickable": False,
                    "selector_candidates": ["a.productos-ElementoLink", "a"],
                },
            ],
        }

        build = propose_selectors(measurement_case, dom_snapshot)

        selector = measurement_case["interacciones"][0]["selector_candidato"]
        self.assertIsNotNone(selector)
        self.assertIn("a.productos-filtro_categoria", selector)
        self.assertNotIn(",", selector)
        self.assertEqual(measurement_case["interacciones"][0]["match_count"], 3)


if __name__ == "__main__":
    unittest.main()
