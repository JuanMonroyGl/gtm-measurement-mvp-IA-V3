import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.processing.selectors.build_selectors import propose_selectors
from core.processing.selectors.validate_selectors import validate_selector_candidates


def test_selector_from_observed_inventory_only():
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
        "state_html": {
            "initial_render": '<html><body><button id="pay-btn">Pagar ahora</button></body></html>'
        },
        "clickable_inventory": [
            {
                "tag": "button",
                "text": "Pagar ahora",
                "aria_label": None,
                "title": None,
                "href": None,
                "id": "pay-btn",
                "class_list": [],
                "ancestors": [],
                "outer_html_excerpt": '<button id="pay-btn">Pagar ahora</button>',
                "bounding_box": None,
                "state": "initial_render",
                "is_visible": True,
                "is_clickable": True,
                "selector_candidates": ["#pay-btn", "button"],
            }
        ],
    }

    build = propose_selectors(measurement_case, dom_snapshot)
    validate_selector_candidates(measurement_case, dom_snapshot, build.get("selector_evidence"))

    assert measurement_case["interacciones"][0]["selector_candidato"] == "#pay-btn"


def test_selector_null_when_not_observed():
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
        "state_html": {
            "initial_render": '<html><body><button id="pay-btn">Pagar ahora</button></body></html>'
        },
        "clickable_inventory": [],
    }

    build = propose_selectors(measurement_case, dom_snapshot)
    validate_selector_candidates(measurement_case, dom_snapshot, build.get("selector_evidence"))

    assert measurement_case["interacciones"][0]["selector_candidato"] is None
    assert any("human_review_required" in w for w in measurement_case["interacciones"][0]["warnings"])
