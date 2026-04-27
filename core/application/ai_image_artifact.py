"""Load AI image extraction artifacts for the main pipeline."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from core.cli.context import CaseContext


AI_IMAGE_STRUCTURED_RELATIVE = Path("IA") / "imagenes" / "image_text_structured.json"


def ai_image_structured_path(context: CaseContext) -> Path:
    return context.repo_root / "outputs" / context.case_id / AI_IMAGE_STRUCTURED_RELATIVE


def _extract_urls(text: str | None) -> list[str]:
    if not text:
        return []
    return re.findall(r"https?://\S+", text)


def _as_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _interaction_mode_from_ai_item(item: dict[str, Any], element_variants: list[str], title_variants: list[str]) -> str:
    mode = str(item.get("interaction_mode") or "").strip().lower()
    event = str(item.get("tipo_evento") or "").strip().lower()
    has_multiple = len(element_variants) > 1 or len(title_variants) > 1
    if has_multiple:
        return "group"
    if event not in {"clic menu", "clic tab", "clic card"}:
        return "single"
    return mode or "single"


def load_ai_image_structured_artifact(context: CaseContext) -> dict[str, Any]:
    path = ai_image_structured_path(context)
    if not path.exists():
        return {
            "available": False,
            "path": str(path),
            "warnings": [],
        }

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {
            "available": False,
            "path": str(path),
            "warnings": [f"AI image structured artifact JSON invalido: linea {exc.lineno}, columna {exc.colno}."],
        }

    interactions = [item for item in (payload.get("interactions") or []) if isinstance(item, dict)]
    warnings: list[str] = []
    if not interactions:
        warnings.append("AI image structured artifact disponible pero sin interacciones.")

    return {
        "available": bool(interactions),
        "path": str(path),
        "payload": payload,
        "interactions": interactions,
        "warnings": warnings,
    }


def parsed_plan_from_ai_image_artifact(context: CaseContext, artifact: dict[str, Any]) -> dict[str, Any] | None:
    if not artifact.get("available"):
        return None

    payload = artifact.get("payload") or {}
    interactions = artifact.get("interactions") or []
    images = [item for item in (payload.get("images") or []) if isinstance(item, dict)]
    plan_url_candidates: list[str] = []
    evidence: list[dict[str, Any]] = []

    for image in images:
        extracted_text = image.get("extracted_text")
        urls = _extract_urls(extracted_text)
        plan_url_candidates.extend(urls)
        evidence.append(
            {
                "image_path": str(image.get("image_name") or ""),
                "extracted_lines": str(extracted_text or "").splitlines(),
                "extracted_text": extracted_text,
                "extraction_method": "openai_image_text_structured_artifact",
                "confidence": image.get("confidence"),
                "plan_url_candidates": urls,
            }
        )

    interactions_raw: list[dict[str, Any]] = []
    for item in interactions:
        warnings = []
        if item.get("warning"):
            warnings.append(str(item["warning"]))
        warnings.append("Interaccion cargada desde outputs/<case_id>/IA/imagenes/image_text_structured.json.")

        source_image = str(item.get("source_image") or "")
        element_variants = _as_list(item.get("element_variants"))
        title_variants = _as_list(item.get("title_variants"))
        fields = {
            "tipo_evento": item.get("tipo_evento"),
            "activo": item.get("activo"),
            "seccion": item.get("seccion"),
            "flujo": item.get("flujo"),
            "elemento": item.get("elemento"),
            "titulo_card": item.get("titulo_card"),
            "ubicacion": item.get("ubicacion"),
            "texto_referencia": item.get("texto_referencia"),
            "interaction_mode": _interaction_mode_from_ai_item(item, element_variants, title_variants),
            "element_variants": element_variants,
            "title_variants": title_variants,
            "group_context": item.get("group_context"),
            "zone_hint": item.get("zone_hint"),
            "value_extraction_strategy": item.get("value_extraction_strategy"),
        }
        interactions_raw.append(
            {
                "source_image": source_image,
                "fields": fields,
                "plan_url_candidates": list(dict.fromkeys(plan_url_candidates)),
                "confidence": item.get("confidence"),
                "warnings": warnings,
            }
        )

    return {
        "parser_status": "ok" if interactions_raw else "partial",
        "image_count": len(images) or len(interactions_raw),
        "evidence": evidence,
        "interactions_raw": interactions_raw,
        "ocr_status": {
            "ocr_available": None,
            "source": "openai_image_text_structured_artifact",
        },
        "warnings": [
            f"Plan cargado desde artefacto IA local: {artifact.get('path')}.",
            *list(artifact.get("warnings") or []),
        ],
        "ai_image_structured_artifact": {
            "available": True,
            "used": True,
            "path": artifact.get("path"),
            "provider": payload.get("provider"),
            "model": payload.get("model"),
            "image_detail": payload.get("image_detail"),
            "image_source": payload.get("image_source"),
            "interactions": len(interactions_raw),
        },
    }
