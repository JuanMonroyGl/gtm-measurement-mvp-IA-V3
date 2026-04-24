"""Parallel AI image text extraction flow.

This module writes diagnostic artifacts only. It does not feed the main
measurement pipeline, selector proposal, scraping, or GTM generation.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

from openai import OpenAIError
from pydantic import BaseModel, Field

from core.ai.config import AIConfig
from core.ai.contracts import Interaction
from core.ai.openai_client import get_openai_client
from core.cli.context import CaseContext
from core.cli.errors import UserFacingError
from core.intake.prepare_case_assets import CaseAssetPreparationError, prepare_case_assets


PROMPT_VERSION = "ai_image_text_extraction_parallel_v1"
SUPPORTED_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}


class ImageExtraction(BaseModel):
    extracted_text: str | None = None
    activo: str | None = None
    seccion: str | None = None
    interactions: list[Interaction] = Field(default_factory=list)
    confidence: float | None = 0.0
    warnings: list[str] = Field(default_factory=list)


def _to_data_url(path: Path) -> str:
    mime = "image/png"
    if path.suffix.lower() in {".jpg", ".jpeg"}:
        mime = "image/jpeg"
    elif path.suffix.lower() == ".webp":
        mime = "image/webp"
    encoded = base64.b64encode(path.read_bytes()).decode("utf-8")
    return f"data:{mime};base64,{encoded}"


def _usage_to_dict(usage: Any) -> dict[str, Any]:
    if usage is None:
        return {}
    if hasattr(usage, "model_dump"):
        return usage.model_dump()
    if isinstance(usage, dict):
        return usage
    return {
        key: getattr(usage, key)
        for key in ("input_tokens", "output_tokens", "total_tokens")
        if hasattr(usage, key)
    }


def _add_usage(aggregate: dict[str, int], usage: dict[str, Any]) -> None:
    for key in ("input_tokens", "output_tokens", "total_tokens"):
        value = usage.get(key)
        if isinstance(value, int):
            aggregate[key] = aggregate.get(key, 0) + value


def _image_paths(context: CaseContext) -> tuple[list[Path], str]:
    candidates = [
        (context.case_dir / "images", "inputs_images"),
        (context.repo_root / "outputs" / context.case_id / "prepared_assets" / "images", "prepared_assets_images"),
    ]
    images_dir = next((path for path, _source in candidates if path.exists()), None)
    source = next((_source for path, _source in candidates if path.exists()), None)
    if images_dir is None or source is None:
        checked = ", ".join(str(path) for path, _source in candidates)
        raise UserFacingError(f"No existe carpeta de imagenes. Rutas revisadas: {checked}")
    paths = sorted(
        path
        for path in images_dir.iterdir()
        if path.is_file() and path.suffix.lower() in SUPPORTED_IMAGE_SUFFIXES
    )
    if not paths:
        raise UserFacingError(f"No hay imagenes PNG/JPG/WEBP en {images_dir}")
    return paths, source


def _ensure_image_paths(context: CaseContext) -> tuple[list[Path], str]:
    try:
        return _image_paths(context)
    except UserFacingError:
        try:
            prepare_case_assets(context=context)
        except CaseAssetPreparationError as exc:
            raise UserFacingError(f"No se pudieron preparar imagenes para IA: {exc}") from exc
        return _image_paths(context)


def _build_input(image_path: Path, config: AIConfig) -> list[dict[str, Any]]:
    return [
        {
            "role": "user",
            "content": [
                {
                    "type": "input_text",
                    "text": (
                        "Eres un extractor estructurado de planes de medicion para GTM. "
                        "Tu tarea es leer la imagen y devolver datos estructurados compatibles con el esquema ImageExtraction. "
                        "Extrae unicamente informacion visible o claramente deducible del plan. "
                        "No inventes campos, URLs, eventos, selectores CSS, nombres de secciones ni textos que no esten en la imagen. "
                        "Si algo no es legible o no aparece, usa null, lista vacia o agrega un warning claro. "
                        "Incluye extracted_text con el texto visible de la imagen lo mas fiel posible, respetando eventos, campos, valores, URLs, saltos relevantes y orden visual. "
                        "Debes detectar interacciones con estos campos cuando existan en el plan: "
                        "tipo_evento, flujo, ubicacion, elemento, element_variants, titulo_card, title_variants, "
                        "texto_referencia, interaction_mode, group_context, zone_hint, value_extraction_strategy, confidence y warning. "
                        "Tipos de evento permitidos: Clic Menu, Clic Tab, Clic Card, Clic Boton, Clic Link, Clic Tap. "
                        "Usa exactamente esos nombres cuando el plan muestre equivalentes claros. "
                        "Reglas obligatorias para variantes: "
                        "Si elemento contiene una plantilla tipo {{...|...}} con dos o mas variantes separadas por |, interaction_mode debe ser \"group\". "
                        "Extrae cada opcion en element_variants como una lista limpia, sin llaves, sin pipes, sin saltos de linea innecesarios y sin espacios sobrantes. "
                        "Conserva elemento como plantilla canonica en formato {{variante 1|variante 2|variante 3}} cuando el plan lo muestre como plantilla. "
                        "Si titulo card, titulo_card o un campo equivalente contiene una plantilla tipo {{...|...}} con dos o mas variantes separadas por |, interaction_mode debe ser \"group\". "
                        "Extrae cada opcion en title_variants como una lista limpia, sin llaves, sin pipes, sin saltos de linea innecesarios y sin espacios sobrantes. "
                        "Conserva titulo_card como plantilla canonica cuando el campo exista en el plan. "
                        "Nunca uses interaction_mode=\"single\" si element_variants tiene mas de un valor. "
                        "Nunca uses interaction_mode=\"single\" si title_variants tiene mas de un valor. "
                        "Usa interaction_mode=\"single\" solo cuando la interaccion sea una accion unica clara y no existan multiples variantes. "
                        "Reglas obligatorias de group_context y zone_hint: "
                        "Si tipo_evento es \"Clic Menu\" y hay multiples variantes, usa group_context=\"top_navigation\" y zone_hint=\"header-menu\". "
                        "Si tipo_evento es \"Clic Menu\" y no hay multiples variantes, usa interaction_mode=\"single\" salvo que el plan indique claramente una coleccion. "
                        "Si tipo_evento es \"Clic Card\" y hay multiples variantes en elemento o titulo_card, "
                        "usa group_context=\"card_collection\", zone_hint=\"card-grid\" y value_extraction_strategy=\"prefer_title_variant_then_click_text\". "
                        "Si tipo_evento es \"Clic Tab\" y la ubicacion, titulo de bloque o contexto visible indica una zona de preguntas frecuentes, "
                        "dudas frecuentes, consultas frecuentes, FAQ, lo mas consultado, temas mas consultados o contenidos de ayuda tipo listado de preguntas, "
                        "usa group_context=\"faq_collection\" y zone_hint=\"faq-list\". "
                        "No clasifiques como faq_collection solo porque una variante individual diga \"centro de ayuda\"; debe haber senal de que la zona completa es de preguntas, ayuda o consultas frecuentes. "
                        "Si tipo_evento es \"Clic Tab\" y la interaccion representa accesos rapidos, atajos, opciones horizontales, tabs del medio, carrusel de accesos, "
                        "botones con iconos, modulos de navegacion intermedia o shortcuts, usa group_context=\"shortcut_collection\" y zone_hint=\"shortcut-tabs\". "
                        "Si tipo_evento es \"Clic Tab\" pero no hay evidencia suficiente para decidir entre faq_collection y shortcut_collection, "
                        "usa group_context=\"generic_tab_collection\" y zone_hint=\"generic-tabs\", con warning breve explicando la ambiguedad. "
                        "Reglas de value_extraction_strategy: "
                        "Para Clic Menu grupal usa \"match_element_variant_from_clicked_text\". "
                        "Para Clic Tab grupal usa \"match_element_variant_from_clicked_text\". "
                        "Para Clic Card con title_variants usa \"prefer_title_variant_then_click_text\". "
                        "Para Clic Card sin title_variants usa \"match_element_variant_from_clicked_text\" si hay variantes de elemento. "
                        "Para interacciones single usa \"click_text\" salvo que el plan indique otra logica clara. "
                        "Reglas de normalizacion: "
                        "Limpia espacios dobles, saltos internos innecesarios y fragmentos partidos por OCR, pero conserva el sentido exacto del texto. "
                        "No unas varias variantes en un unico string. "
                        "No dejes element_variants vacio si elemento contiene opciones separadas por |. "
                        "No dejes title_variants vacio si titulo_card contiene opciones separadas por |. "
                        "No elimines palabras importantes de elemento, ubicacion, flujo, titulo_card ni texto_referencia. "
                        "No conviertas un grupo de variantes en una sola frase resumida. "
                        "Reglas de confianza y warnings: "
                        "Usa confidence alto solo si el texto del plan se lee con claridad. "
                        "Si aplicas reglas estructurales evidentes del plan, no lo marques como warning. "
                        "Agrega warning solo si hay texto ilegible, conflicto entre campos, evento incompleto, clasificacion ambigua o inferencia debil. "
                        "Restricciones estrictas: "
                        "No propongas selectores CSS. "
                        "No analices DOM. "
                        "No generes codigo GTM. "
                        "No uses informacion del HTML, del golden, de archivos manuales ni de casos previos. "
                        "No sobreajustes la salida a un caso especifico. "
                        "Solo extrae y estructura el plan de medicion visible en la imagen."
                    ),
                },
                {
                    "type": "input_image",
                    "image_url": _to_data_url(image_path),
                    "detail": config.image_detail,
                },
            ],
        }
    ]


def _normalize_text(value: Any) -> str:
    return str(value or "").strip().lower()


def _postprocess_interaction(interaction: dict[str, Any]) -> dict[str, Any]:
    item = dict(interaction)
    warnings = []
    if item.get("warning"):
        warnings.append(str(item["warning"]))

    element_variants = [str(value).strip() for value in (item.get("element_variants") or []) if str(value).strip()]
    title_variants = [str(value).strip() for value in (item.get("title_variants") or []) if str(value).strip()]
    item["element_variants"] = element_variants
    item["title_variants"] = title_variants

    has_group_variants = len(element_variants) > 1 or len(title_variants) > 1
    if has_group_variants and item.get("interaction_mode") != "group":
        item["interaction_mode"] = "group"
        warnings.append("interaction_mode corregido a group por multiples variantes.")
    elif not item.get("interaction_mode"):
        item["interaction_mode"] = "group" if has_group_variants else "single"

    event_type = _normalize_text(item.get("tipo_evento"))
    location = _normalize_text(item.get("ubicacion"))
    context_text = _normalize_text(
        " ".join(
            [
                str(item.get("elemento") or ""),
                str(item.get("titulo_card") or ""),
                location,
                " ".join(element_variants),
                " ".join(title_variants),
            ]
        )
    )

    if item["interaction_mode"] == "group" and event_type == "clic menu":
        item["group_context"] = item.get("group_context") or "top_navigation"
        item["zone_hint"] = item.get("zone_hint") or "header-menu"
        item["value_extraction_strategy"] = item.get("value_extraction_strategy") or "match_element_variant_from_clicked_text"
    if item["interaction_mode"] == "group" and event_type == "clic card":
        item["group_context"] = item.get("group_context") or "card_collection"
        item["zone_hint"] = item.get("zone_hint") or "card-grid"
        if title_variants:
            item["value_extraction_strategy"] = "prefer_title_variant_then_click_text"
        else:
            item["value_extraction_strategy"] = item.get("value_extraction_strategy") or "match_element_variant_from_clicked_text"
    if item["interaction_mode"] == "group" and event_type == "clic tab":
        faq_signals = ("preguntas", "frecuentes", "faq", "consultado", "consultas", "ayuda")
        strong_faq_signals = ("preguntas", "frecuentes", "faq", "consultado", "consultas")
        shortcut_signals = ("tab", "tabs", "atajo", "acceso", "rapido", "icono", "medio", "shortcut", "carrusel")
        if any(signal in context_text for signal in strong_faq_signals) or (
            "ayuda" in context_text and "centro de ayuda" not in context_text
        ):
            item["group_context"] = item.get("group_context") or "faq_collection"
            item["zone_hint"] = item.get("zone_hint") or "faq-list"
        elif any(signal in context_text for signal in shortcut_signals):
            item["group_context"] = item.get("group_context") or "shortcut_collection"
            item["zone_hint"] = item.get("zone_hint") or "shortcut-tabs"
        else:
            item["group_context"] = item.get("group_context") or "generic_tab_collection"
            item["zone_hint"] = item.get("zone_hint") or "generic-tabs"
            warnings.append("clasificacion tab grupal ambigua.")
        item["value_extraction_strategy"] = item.get("value_extraction_strategy") or "match_element_variant_from_clicked_text"

    item["warning"] = "; ".join(dict.fromkeys(warnings)) if warnings else None
    return item


def _postprocess_parsed_payload(payload: dict[str, Any]) -> dict[str, Any]:
    cleaned = dict(payload)
    cleaned["interactions"] = [
        _postprocess_interaction(interaction)
        for interaction in (cleaned.get("interactions") or [])
        if isinstance(interaction, dict)
    ]
    return cleaned


def _extract_one_image(*, image_path: Path, config: AIConfig) -> dict[str, Any]:
    client = get_openai_client()
    input_payload = _build_input(image_path, config)
    warnings: list[str] = []
    try:
        response = client.responses.parse(
            model=config.model_image,
            input=input_payload,
            text_format=ImageExtraction,
            max_output_tokens=config.max_tokens_image,
            reasoning={"effort": "minimal"},
        )
        parsed = response.output_parsed
        if parsed is None:
            warnings.append("OpenAI no devolvio ImageExtraction parseable.")
            parsed_payload = ImageExtraction(warnings=warnings).model_dump()
        else:
            parsed_payload = _postprocess_parsed_payload(parsed.model_dump())
            parsed_payload["warnings"] = list(dict.fromkeys([*parsed_payload.get("warnings", []), *warnings]))
        return {
            "image_path": str(image_path),
            "image_name": image_path.name,
            "status": getattr(response, "status", None),
            "response_id": getattr(response, "id", None),
            "usage": _usage_to_dict(getattr(response, "usage", None)),
            "parsed": parsed_payload,
        }
    except OpenAIError as exc:
        return {
            "image_path": str(image_path),
            "image_name": image_path.name,
            "status": "error",
            "response_id": None,
            "usage": {},
            "parsed": ImageExtraction(warnings=[f"OpenAI image extraction error: {exc}"]).model_dump(),
        }


def _render_markdown(case_id: str, results: list[dict[str, Any]], aggregate_usage: dict[str, int]) -> str:
    lines = [
        f"# IA imagenes {case_id}",
        "",
        "## Uso",
        f"- input_tokens: {aggregate_usage.get('input_tokens')}",
        f"- output_tokens: {aggregate_usage.get('output_tokens')}",
        f"- total_tokens: {aggregate_usage.get('total_tokens')}",
        "",
        "## Imagenes",
    ]
    for result in results:
        parsed = result.get("parsed") or {}
        lines.extend(
            [
                f"### {result.get('image_name')}",
                f"- status: {result.get('status')}",
                f"- response_id: {result.get('response_id')}",
                f"- confidence: {parsed.get('confidence')}",
                f"- warnings: {parsed.get('warnings')}",
                "",
                "```text",
                str(parsed.get("extracted_text") or "").strip(),
                "```",
                "",
            ]
        )
    return "\n".join(lines)


def run_ai_image_extraction(context: CaseContext) -> dict[str, Any]:
    config = AIConfig.from_env()
    if not config.enabled or config.provider != "openai":
        raise UserFacingError("AI image extraction requiere AI_ENABLED=true y AI_PROVIDER=openai.")

    case_dir = context.case_dir
    images, image_source = _ensure_image_paths(context)
    output_dir = context.repo_root / "outputs" / context.case_id / "IA" / "imagenes"
    output_dir.mkdir(parents=True, exist_ok=True)

    results = [_extract_one_image(image_path=image_path, config=config) for image_path in images]
    aggregate_usage: dict[str, int] = {}
    for result in results:
        _add_usage(aggregate_usage, result.get("usage") or {})

    interactions = []
    for result in results:
        parsed = result.get("parsed") or {}
        for interaction in parsed.get("interactions") or []:
            item = dict(interaction)
            item["source_image"] = result.get("image_name")
            item["source"] = "openai_image_text_extraction"
            interactions.append(item)

    raw_payload = {
        "artifact_type": "parallel_ai_image_text_raw",
        "case_id": context.case_id,
        "provider": config.provider,
        "model": config.model_image,
        "image_detail": config.image_detail,
        "image_source": image_source,
        "prompt_version": PROMPT_VERSION,
        "images": results,
    }
    structured_payload = {
        "artifact_type": "parallel_ai_image_text_structured",
        "case_id": context.case_id,
        "provider": config.provider,
        "model": config.model_image,
        "image_detail": config.image_detail,
        "image_source": image_source,
        "interactions": interactions,
        "images": [
            {
                "image_name": result.get("image_name"),
                "extracted_text": (result.get("parsed") or {}).get("extracted_text"),
                "activo": (result.get("parsed") or {}).get("activo"),
                "seccion": (result.get("parsed") or {}).get("seccion"),
                "confidence": (result.get("parsed") or {}).get("confidence"),
                "warnings": (result.get("parsed") or {}).get("warnings"),
            }
            for result in results
        ],
    }
    usage_payload = {
        "artifact_type": "parallel_ai_image_token_usage",
        "case_id": context.case_id,
        "provider": config.provider,
        "model": config.model_image,
        "image_detail": config.image_detail,
        "image_source": image_source,
        "aggregate_usage": aggregate_usage,
        "by_image": [
            {
                "image_name": result.get("image_name"),
                "usage": result.get("usage") or {},
                "status": result.get("status"),
                "response_id": result.get("response_id"),
            }
            for result in results
        ],
    }

    raw_path = output_dir / "image_text_raw.json"
    structured_path = output_dir / "image_text_structured.json"
    markdown_path = output_dir / "image_text_by_image.md"
    usage_path = output_dir / "token_usage.json"
    report_path = output_dir / "extraction_report.md"

    raw_path.write_text(json.dumps(raw_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    structured_path.write_text(json.dumps(structured_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    usage_path.write_text(json.dumps(usage_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown = _render_markdown(context.case_id, results, aggregate_usage)
    markdown_path.write_text(markdown, encoding="utf-8")
    report_path.write_text(markdown, encoding="utf-8")

    return {
        "case_id": context.case_id,
        "output_dir": str(output_dir),
        "images_processed": len(images),
        "image_source": image_source,
        "model": config.model_image,
        "image_detail": config.image_detail,
        "aggregate_usage": aggregate_usage,
        "outputs": {
            "image_text_raw": str(raw_path),
            "image_text_structured": str(structured_path),
            "image_text_by_image": str(markdown_path),
            "token_usage": str(usage_path),
            "extraction_report": str(report_path),
        },
    }
