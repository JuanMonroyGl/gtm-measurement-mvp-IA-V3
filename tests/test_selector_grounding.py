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

    def test_single_interactions_with_same_text_get_distinct_selectors(self) -> None:
        measurement_case = {
            "activo": "bancolombia",
            "seccion": "personas",
            "interacciones": [
                {
                    "tipo_evento": "Clic Boton",
                    "flujo": "futbol_fanfest",
                    "elemento": "{{inscribete ahora}}",
                    "element_variants": ["inscribete ahora"],
                    "ubicacion": "header",
                    "texto_referencia": None,
                    "selector_candidato": None,
                    "selector_activador": None,
                    "match_count": None,
                    "warnings": [],
                },
                {
                    "tipo_evento": "Clic Boton",
                    "flujo": "futbol_fanfest",
                    "elemento": "{{inscribete ahora}}",
                    "element_variants": ["inscribete ahora"],
                    "ubicacion": "asi reclamas tus boletas",
                    "texto_referencia": "Inscribete ahora boton resaltado",
                    "selector_candidato": None,
                    "selector_activador": None,
                    "match_count": None,
                    "warnings": [],
                },
            ],
        }
        dom_snapshot = {
            "render_engine": "playwright_multi_state",
            "state_html": {
                "initial_render": (
                    '<html><body>'
                    '<section><a class="hero-cta" href="/inscripcion" data-gtm-mvp-node-id="node-1">Inscribete ahora</a></section>'
                    '<section><a class="section-cta" href="/inscripcion" data-gtm-mvp-node-id="node-2">Inscribete ahora</a></section>'
                    '<button id="boton-banner-mobile" class="boton-banner-mobile" data-gtm-mvp-node-id="node-3"></button>'
                    "</body></html>"
                )
            },
            "clickable_inventory": [
                {
                    "node_id": "node-1",
                    "tag": "a",
                    "text": "Inscribete ahora",
                    "context_text": "Header Inscribete ahora",
                    "aria_label": None,
                    "title": None,
                    "href": "/inscripcion",
                    "id": None,
                    "class_list": ["hero-cta"],
                    "ancestors": [],
                    "outer_html_excerpt": '<a class="hero-cta" href="/inscripcion">Inscribete ahora</a>',
                    "bounding_box": None,
                    "state": "initial_render",
                    "source": "observed_rendered_dom",
                    "is_visible": True,
                    "is_clickable": True,
                    "selector_candidates": ['a[href="/inscripcion"]', "a.hero-cta", "a"],
                },
                {
                    "node_id": "node-2",
                    "tag": "a",
                    "text": "Inscribete ahora",
                    "context_text": "Descubre como participar Inscribete ahora",
                    "aria_label": None,
                    "title": None,
                    "href": "/inscripcion",
                    "id": None,
                    "class_list": ["section-cta"],
                    "ancestors": [],
                    "outer_html_excerpt": '<a class="section-cta" href="/inscripcion">Inscribete ahora</a>',
                    "bounding_box": None,
                    "state": "initial_render",
                    "source": "observed_rendered_dom",
                    "is_visible": True,
                    "is_clickable": True,
                    "selector_candidates": ['a[href="/inscripcion"]', "a.section-cta", "a"],
                },
                {
                    "node_id": "node-3",
                    "tag": "button",
                    "text": "",
                    "context_text": "Inscribete ahora",
                    "aria_label": None,
                    "title": None,
                    "href": None,
                    "id": "boton-banner-mobile",
                    "class_list": ["boton-banner-mobile"],
                    "ancestors": [],
                    "outer_html_excerpt": '<button id="boton-banner-mobile" class="boton-banner-mobile"></button>',
                    "bounding_box": None,
                    "state": "initial_render",
                    "source": "observed_rendered_dom",
                    "is_visible": True,
                    "is_clickable": True,
                    "selector_candidates": ["#boton-banner-mobile", "button.boton-banner-mobile", "button"],
                },
            ],
        }

        build = propose_selectors(measurement_case, dom_snapshot)
        validate_selector_candidates(measurement_case, dom_snapshot, build.get("selector_evidence"))

        selectors = [item["selector_candidato"] for item in measurement_case["interacciones"]]
        self.assertEqual(selectors, ["a.hero-cta", "a.section-cta"])
        self.assertIn("a.section-cta", build_tag_template(measurement_case))

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

    def test_clic_link_long_card_text_variants_promote_compound_href_selector(self) -> None:
        first_variant = "ofertas precios mas bajos facilidades de pago bonos de descuento y mucho mas"
        second_variant = (
            "soy yo conoce como realizar tus tramites de una forma rapida privada y segura "
            "con nuestro nuevo aliado"
        )
        measurement_case = {
            "activo": "bancolombia",
            "seccion": "personas",
            "interacciones": [
                {
                    "tipo_evento": "Clic Link",
                    "interaction_mode": "group",
                    "group_context": "clic_link_beneficios",
                    "zone_hint": "beneficios",
                    "element_variants": [first_variant, second_variant],
                    "flujo": "beneficios",
                    "ubicacion": "beneficios",
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
                    '<html><body><section id="cardBoxes"><div class="bc-row">'
                    '<a href="/personas/beneficios/ofertas" data-gtm-mvp-node-id="node-1">'
                    "<h3>Ofertas</h3>"
                    "<p>Precios m\u00e1s bajos, facilidades de pago, bonos de descuentos y mucho m\u00e1s.</p>"
                    "</a>"
                    '<a href="/personas/necesidades/mas-beneficios/soy-yo-app" data-gtm-mvp-node-id="node-2">'
                    "<h3>Soy yo</h3>"
                    "<p>Conoce c\u00f3mo realizar tus tr\u00e1mites de una forma r\u00e1pida, privada y segura con nuestro nuevo aliado.</p>"
                    "</a>"
                    "</div></section></body></html>"
                )
            },
            "clickable_inventory": [
                {
                    "node_id": "node-1",
                    "tag": "a",
                    "text": "Ofertas Precios m\u00e1s bajos, facilidades de pago, bonos de descuentos y mucho m\u00e1s.",
                    "context_text": (
                        "Ofertas Precios m\u00e1s bajos, facilidades de pago, bonos de descuentos y mucho m\u00e1s. "
                        "Soy yo Conoce c\u00f3mo realizar tus tr\u00e1mites de una forma r\u00e1pida, privada y segura "
                        "con nuestro nuevo aliado."
                    ),
                    "aria_label": None,
                    "title": None,
                    "href": "/personas/beneficios/ofertas",
                    "id": None,
                    "class_list": [],
                    "ancestors": [
                        {"tag": "div", "id": None, "classes": ["bc-row"]},
                        {"tag": "section", "id": "cardBoxes", "classes": []},
                    ],
                    "outer_html_excerpt": '<a href="/personas/beneficios/ofertas">Ofertas</a>',
                    "bounding_box": None,
                    "state": "initial_render",
                    "source": "observed_rendered_dom",
                    "is_visible": True,
                    "is_clickable": True,
                    "selector_candidates": ['a[href="/personas/beneficios/ofertas"]', "a"],
                },
                {
                    "node_id": "node-2",
                    "tag": "a",
                    "text": (
                        "Soy yo Conoce c\u00f3mo realizar tus tr\u00e1mites de una forma r\u00e1pida, privada y segura "
                        "con nuestro nuevo aliado."
                    ),
                    "context_text": (
                        "Ofertas Precios m\u00e1s bajos, facilidades de pago, bonos de descuentos y mucho m\u00e1s. "
                        "Soy yo Conoce c\u00f3mo realizar tus tr\u00e1mites de una forma r\u00e1pida, privada y segura "
                        "con nuestro nuevo aliado."
                    ),
                    "aria_label": None,
                    "title": None,
                    "href": "/personas/necesidades/mas-beneficios/soy-yo-app",
                    "id": None,
                    "class_list": [],
                    "ancestors": [
                        {"tag": "div", "id": None, "classes": ["bc-row"]},
                        {"tag": "section", "id": "cardBoxes", "classes": []},
                    ],
                    "outer_html_excerpt": '<a href="/personas/necesidades/mas-beneficios/soy-yo-app">Soy yo</a>',
                    "bounding_box": None,
                    "state": "initial_render",
                    "source": "observed_rendered_dom",
                    "is_visible": True,
                    "is_clickable": True,
                    "selector_candidates": ['a[href="/personas/necesidades/mas-beneficios/soy-yo-app"]', "a"],
                },
            ],
        }

        build = propose_selectors(measurement_case, dom_snapshot)
        validate_selector_candidates(measurement_case, dom_snapshot, build.get("selector_evidence"))

        interaction = measurement_case["interacciones"][0]
        self.assertTrue(build["selector_evidence"][0]["promoted"], build["selector_evidence"][0].get("rejection_reason"))
        self.assertEqual(
            interaction["selector_candidato"],
            'a[href="/personas/beneficios/ofertas"], a[href="/personas/necesidades/mas-beneficios/soy-yo-app"]',
        )
        self.assertEqual(interaction["selector_contenedor"], "#cardBoxes")
        self.assertEqual(interaction["match_count"], 2)
        self.assertIn('a[href="/personas/necesidades/mas-beneficios/soy-yo-app"] *', interaction["selector_activador"])

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

    def test_single_prefers_exact_element_variant_over_long_context_container(self) -> None:
        measurement_case = {
            "activo": "bancolombia",
            "seccion": "personas",
            "interacciones": [
                {
                    "tipo_evento": "Clic Boton",
                    "interaction_mode": "single",
                    "elemento": "{{quiero registrarme}}",
                    "element_variants": ["quiero registrarme"],
                    "flujo": "puntos colombia",
                    "ubicacion": "menu principal",
                    "texto_referencia": (
                        "Puntos Colombia Ser parte de Puntos Colombia no tiene costo y una vez registrado, "
                        "estaras listo para empezar a disfrutar de tus puntos"
                    ),
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
                    '<a class="bc-button-primary bc-button-default" data-gtm-mvp-node-id="node-1">Quiero registrarme</a>'
                    '<div class="bc-accordions-group bc-multiple" role="group" tabindex="undefined" '
                    'data-gtm-mvp-node-id="node-2">'
                    'Si pertenecia a Puntos Bancolombia, debo registrarme en Puntos Colombia'
                    "</div>"
                    "</body></html>"
                )
            },
            "clickable_inventory": [
                {
                    "node_id": "node-1",
                    "tag": "a",
                    "text": "Quiero registrarme",
                    "context_text": measurement_case["interacciones"][0]["texto_referencia"],
                    "aria_label": None,
                    "title": None,
                    "href": None,
                    "id": None,
                    "class_list": ["bc-button-primary", "bc-button-default"],
                    "ancestors": [],
                    "outer_html_excerpt": '<a class="bc-button-primary bc-button-default">Quiero registrarme</a>',
                    "bounding_box": None,
                    "state": "initial_render",
                    "source": "observed_rendered_dom",
                    "is_visible": True,
                    "is_clickable": True,
                    "selector_candidates": ["a.bc-button-primary.bc-button-default", "a"],
                },
                {
                    "node_id": "node-2",
                    "tag": "div",
                    "text": "Si pertenecia a Puntos Bancolombia, debo registrarme en Puntos Colombia",
                    "context_text": "Preguntas frecuentes Puntos Colombia registrarme",
                    "aria_label": None,
                    "title": None,
                    "href": None,
                    "id": None,
                    "class_list": ["bc-accordions-group", "bc-multiple"],
                    "ancestors": [],
                    "outer_html_excerpt": '<div class="bc-accordions-group bc-multiple">registrarme en Puntos Colombia</div>',
                    "bounding_box": None,
                    "state": "initial_render",
                    "source": "observed_rendered_dom",
                    "is_visible": True,
                    "is_clickable": True,
                    "selector_candidates": ["div.bc-accordions-group.bc-multiple", "div"],
                },
            ],
        }

        build = propose_selectors(measurement_case, dom_snapshot)
        validate_selector_candidates(measurement_case, dom_snapshot, build.get("selector_evidence"))

        self.assertEqual(
            measurement_case["interacciones"][0]["selector_candidato"],
            "a.bc-button-primary.bc-button-default",
        )

    def test_single_prefers_direct_text_over_context_exact_phrase(self) -> None:
        measurement_case = {
            "activo": "bancolombia",
            "seccion": "personas",
            "interacciones": [
                {
                    "tipo_evento": "Clic Boton",
                    "interaction_mode": "single",
                    "elemento": "{{conoce mas}}",
                    "element_variants": ["conoce mas"],
                    "flujo": "colombianos exterior",
                    "ubicacion": "zaswin",
                    "texto_referencia": "Conoce mas",
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
                    '<section id="formas-de-pago">'
                    '<a class="cards__card" href="/personas/giros/internacionales/remesas/zaswin" '
                    'data-gtm-mvp-node-id="node-card">'
                    "send-money-2 Zaswin Envia plata desde Estados Unidos. Conocer mas"
                    "</a>"
                    "</section>"
                    '<section id="componente-imagen-texto">'
                    '<div class="contenedor-boton">'
                    '<a href="/personas/giros/internacionales/remesas/zaswin" data-gtm-mvp-node-id="node-1">'
                    "Conoce mas"
                    "</a>"
                    "</div>"
                    '<a href="https://api.whatsapp.com/send/?phone=573" data-gtm-mvp-node-id="node-2">'
                    "Habla con Zaswin"
                    "</a>"
                    "</section>"
                    "</body></html>"
                )
            },
            "clickable_inventory": [
                {
                    "node_id": "node-card",
                    "tag": "a",
                    "text": "send-money-2 Zaswin Envia plata desde Estados Unidos. Conocer mas",
                    "context_text": "Soluciones a tu medida Zaswin Conocer mas",
                    "aria_label": None,
                    "title": None,
                    "href": "/personas/giros/internacionales/remesas/zaswin",
                    "id": None,
                    "class_list": ["cards__card"],
                    "ancestors": [{"tag": "section", "id": "formas-de-pago", "classes": []}],
                    "outer_html_excerpt": '<a class="cards__card" href="/personas/giros/internacionales/remesas/zaswin">Zaswin Conocer mas</a>',
                    "bounding_box": None,
                    "state": "initial_render",
                    "source": "observed_rendered_dom",
                    "is_visible": True,
                    "is_clickable": True,
                    "selector_candidates": ['a[href="/personas/giros/internacionales/remesas/zaswin"]', "a.cards__card", "a"],
                },
                {
                    "node_id": "node-1",
                    "tag": "a",
                    "text": "Conoce mas",
                    "context_text": "Zaswin Conocer mas Habla con Zaswin",
                    "aria_label": None,
                    "title": None,
                    "href": "/personas/giros/internacionales/remesas/zaswin",
                    "id": None,
                    "class_list": [],
                    "ancestors": [
                        {"tag": "div", "id": None, "classes": ["contenedor-boton"]},
                        {"tag": "section", "id": "componente-imagen-texto", "classes": []},
                    ],
                    "outer_html_excerpt": '<a href="/personas/giros/internacionales/remesas/zaswin">Conoce mas</a>',
                    "bounding_box": None,
                    "state": "initial_render",
                    "source": "observed_rendered_dom",
                    "is_visible": True,
                    "is_clickable": True,
                    "selector_candidates": ['a[href="/personas/giros/internacionales/remesas/zaswin"]', "a"],
                },
                {
                    "node_id": "node-2",
                    "tag": "a",
                    "text": "Habla con Zaswin",
                    "context_text": "Zaswin Conoce mas Habla con Zaswin",
                    "aria_label": None,
                    "title": None,
                    "href": "https://api.whatsapp.com/send/?phone=573",
                    "id": None,
                    "class_list": [],
                    "ancestors": [{"tag": "section", "id": "componente-imagen-texto", "classes": []}],
                    "outer_html_excerpt": '<a href="https://api.whatsapp.com/send/?phone=573">Habla con Zaswin</a>',
                    "bounding_box": None,
                    "state": "initial_render",
                    "source": "observed_rendered_dom",
                    "is_visible": True,
                    "is_clickable": True,
                    "selector_candidates": ['a[href="https://api.whatsapp.com/send/?phone=573"]', "a"],
                },
            ],
        }

        build = propose_selectors(measurement_case, dom_snapshot)
        validate_selector_candidates(measurement_case, dom_snapshot, build.get("selector_evidence"))

        self.assertEqual(
            measurement_case["interacciones"][0]["selector_candidato"],
            '#componente-imagen-texto a[href="/personas/giros/internacionales/remesas/zaswin"]',
        )

    def test_top_navigation_misclassification_can_use_page_filter_divs(self) -> None:
        variants = ["todos", "administrar dinero", "vivienda", "viajes", "enviar dinero", "regalos", "seguros"]
        measurement_case = {
            "activo": "bancolombia",
            "seccion": "personas",
            "interacciones": [
                {
                    "tipo_evento": "Clic Menu",
                    "interaction_mode": "group",
                    "group_context": "top_navigation",
                    "zone_hint": "header-menu",
                    "element_variants": variants,
                    "flujo": "colombianos exterior",
                    "ubicacion": "soluciones a tu medida",
                    "selector_candidato": None,
                    "selector_activador": None,
                    "match_count": None,
                    "warnings": [],
                }
            ],
        }
        html_items = "".join(
            f'<div class="filter__option-desktop" data-gtm-mvp-node-id="node-{index}">'
            f'<p class="option-desktop__name">{text}</p></div>'
            for index, text in enumerate(variants, start=1)
        )
        inventory = [
            {
                "node_id": f"node-{index}",
                "tag": "div",
                "text": text,
                "context_text": "Soluciones a tu medida Filtra tu busqueda",
                "aria_label": None,
                "title": None,
                "href": None,
                "id": None,
                "class_list": ["filter__option-desktop"],
                "ancestors": [
                    {"tag": "div", "id": None, "classes": ["filters__desktop"]},
                    {"tag": "section", "id": "formas-de-pago", "classes": []},
                ],
                "outer_html_excerpt": f'<div class="filter__option-desktop">{text}</div>',
                "bounding_box": None,
                "state": "initial_render",
                "source": "observed_rendered_dom",
                "is_visible": True,
                "is_clickable": False,
                "selector_candidates": ["div.filter__option-desktop", "div"],
            }
            for index, text in enumerate(variants, start=1)
        ]
        dom_snapshot = {
            "render_engine": "playwright_multi_state",
            "state_html": {
                "initial_render": f'<html><body><section id="formas-de-pago"><div class="filters__desktop">{html_items}</div></section></body></html>'
            },
            "clickable_inventory": inventory,
        }

        build = propose_selectors(measurement_case, dom_snapshot)
        validate_selector_candidates(measurement_case, dom_snapshot, build.get("selector_evidence"))

        interaction = measurement_case["interacciones"][0]
        self.assertTrue(build["selector_evidence"][0]["promoted"], build["selector_evidence"][0].get("rejection_reason"))
        self.assertEqual(interaction["selector_candidato"], "#formas-de-pago div.filter__option-desktop")
        self.assertEqual(interaction["match_count"], 7)

    def test_generic_tab_collection_can_use_stable_accordion_title_divs(self) -> None:
        variants = [
            "terminos y condiciones para la acumulacion persona natural",
            "terminos y condiciones para la acumulacion persona juridica",
            "documentos historicos persona natural",
            "documentos historicos persona juridica",
        ]
        visible_texts = [
            "T\u00e9rminos y Condiciones para la Acumulaci\u00f3n - Persona Natural",
            "T\u00e9rminos y Condiciones para la Acumulaci\u00f3n - Persona Jur\u00eddica",
            "Documentos Hist\u00f3ricos - Persona Natural",
            "Documentos Hist\u00f3ricos - Persona Jur\u00eddica",
        ]
        measurement_case = {
            "activo": "bancolombia",
            "seccion": "personas",
            "interacciones": [
                {
                    "tipo_evento": "Clic Tab",
                    "interaction_mode": "group",
                    "group_context": "generic_tab_collection",
                    "zone_hint": "generic-tabs",
                    "element_variants": variants,
                    "flujo": "puntos colombia",
                    "ubicacion": "conoce informacion adicional del programa puntos colombia",
                    "selector_candidato": None,
                    "selector_activador": None,
                    "match_count": None,
                    "warnings": [],
                }
            ],
        }
        html_items = "".join(
            (
                '<div class="containerAcordeonesInfo"><div class="acordeonInfo">'
                f'<div class="tituloAcordeonInfo" data-gtm-mvp-node-id="node-{index}">'
                f"<span>{text}</span></div></div></div>"
            )
            for index, text in enumerate(visible_texts, start=1)
        )
        inventory = [
            {
                "node_id": f"node-{index}",
                "tag": "div",
                "text": text,
                "context_text": "Conoce informacion adicional del programa Puntos Colombia",
                "aria_label": None,
                "title": None,
                "href": None,
                "id": None,
                "class_list": ["tituloAcordeonInfo"],
                "ancestors": [
                    {"tag": "div", "id": None, "classes": ["acordeonInfo"]},
                    {"tag": "div", "id": None, "classes": ["containerAcordeonesInfo"]},
                    {"tag": "div", "id": None, "classes": ["containerAcordeonesDocumentos"]},
                ],
                "outer_html_excerpt": f'<div class="tituloAcordeonInfo">{text}</div>',
                "bounding_box": None,
                "state": "initial_render",
                "source": "observed_rendered_dom",
                "is_visible": True,
                "is_clickable": False,
                "selector_candidates": ["div.tituloAcordeonInfo", "div"],
            }
            for index, text in enumerate(visible_texts, start=1)
        ]
        dom_snapshot = {
            "render_engine": "playwright_multi_state",
            "state_html": {
                "initial_render": f'<html><body><section class="containerAcordeonesDocumentos">{html_items}</section></body></html>'
            },
            "clickable_inventory": inventory,
        }

        build = propose_selectors(measurement_case, dom_snapshot)
        validate_selector_candidates(measurement_case, dom_snapshot, build.get("selector_evidence"))

        interaction = measurement_case["interacciones"][0]
        self.assertTrue(build["selector_evidence"][0]["promoted"], build["selector_evidence"][0].get("rejection_reason"))
        self.assertIn("div.tituloAcordeonInfo", interaction["selector_candidato"])
        self.assertEqual(interaction["match_count"], 4)
        self.assertEqual(build["selector_evidence"][0]["chosen"]["variant_coverage"], 4)

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

    def test_menu_group_variant_coverage_uses_clicked_item_not_container_context(self) -> None:
        measurement_case = {
            "interacciones": [
                {
                    "tipo_evento": "Clic Menu",
                    "interaction_mode": "group",
                    "group_context": "top_navigation",
                    "zone_hint": "header-menu",
                    "element_variants": ["inicio", "productos", "sectores"],
                    "flujo": "empresariales",
                    "ubicacion": "menu principal",
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
                    '<html><body><nav class="main-menu">'
                    '<a aria-label="Inicio" data-gtm-mvp-node-id="node-1">Inicio</a>'
                    '<button aria-label="Productos" data-gtm-mvp-node-id="node-2">Productos</button>'
                    '<a aria-label="Sectores" data-gtm-mvp-node-id="node-3">Sectores</a>'
                    "</nav></body></html>"
                )
            },
            "clickable_inventory": [
                {
                    "node_id": "node-1",
                    "tag": "a",
                    "text": "Inicio",
                    "context_text": "Inicio Productos Sectores",
                    "aria_label": "Inicio",
                    "title": None,
                    "href": None,
                    "id": None,
                    "class_list": [],
                    "ancestors": [{"tag": "nav", "id": None, "classes": ["main-menu"]}],
                    "outer_html_excerpt": '<a aria-label="Inicio">Inicio</a>',
                    "bounding_box": None,
                    "state": "initial_render",
                    "source": "observed_rendered_dom",
                    "is_visible": True,
                    "is_clickable": True,
                    "selector_candidates": ['a[aria-label="Inicio"]', "a"],
                },
                {
                    "node_id": "node-2",
                    "tag": "button",
                    "text": "Productos",
                    "context_text": "Inicio Productos Sectores",
                    "aria_label": "Productos",
                    "title": None,
                    "href": None,
                    "id": None,
                    "class_list": [],
                    "ancestors": [{"tag": "nav", "id": None, "classes": ["main-menu"]}],
                    "outer_html_excerpt": '<button aria-label="Productos">Productos</button>',
                    "bounding_box": None,
                    "state": "initial_render",
                    "source": "observed_rendered_dom",
                    "is_visible": True,
                    "is_clickable": True,
                    "selector_candidates": ['button[aria-label="Productos"]', "button"],
                },
                {
                    "node_id": "node-3",
                    "tag": "a",
                    "text": "Sectores",
                    "context_text": "Inicio Productos Sectores",
                    "aria_label": "Sectores",
                    "title": None,
                    "href": None,
                    "id": None,
                    "class_list": [],
                    "ancestors": [{"tag": "nav", "id": None, "classes": ["main-menu"]}],
                    "outer_html_excerpt": '<a aria-label="Sectores">Sectores</a>',
                    "bounding_box": None,
                    "state": "initial_render",
                    "source": "observed_rendered_dom",
                    "is_visible": True,
                    "is_clickable": True,
                    "selector_candidates": ['a[aria-label="Sectores"]', "a"],
                },
            ],
        }

        build = propose_selectors(measurement_case, dom_snapshot)
        validate_selector_candidates(measurement_case, dom_snapshot, build.get("selector_evidence"))

        selector = measurement_case["interacciones"][0]["selector_candidato"]
        self.assertTrue(build["selector_evidence"][0]["promoted"], build["selector_evidence"][0]["rejection_reason"])
        self.assertIn('button[aria-label="Productos"]', selector)
        self.assertIn('a[aria-label="Sectores"]', selector)
        self.assertNotEqual(selector, 'a[aria-label="Inicio"]')
        self.assertIn('button[aria-label="Productos"] *', measurement_case["interacciones"][0]["selector_activador"])


if __name__ == "__main__":
    unittest.main()
