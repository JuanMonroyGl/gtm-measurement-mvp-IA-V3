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


def _build_input(image_path: Path, config: AIConfig) -> list[dict[str, Any]]:
    return [
        {
            "role": "user",
            "content": [
                {
                    "type": "input_text",
                    "text": (
                        "Extrae el texto visible de esta imagen de plan de medicion y devuelve una estructura JSON. "
                        "No inventes valores; usa null o listas vacias cuando algo no sea legible. "
                        "Incluye extracted_text con el texto lo mas fiel posible. "
                        "Detecta interacciones con campos tipo_evento, flujo, ubicacion, elemento, "
                        "element_variants, titulo_card, title_variants, texto_referencia, interaction_mode, "
                        "group_context, zone_hint, value_extraction_strategy, confidence y warning. "
                        "Tipos permitidos: Clic Menu, Clic Tab, Clic Card, Clic Boton, Clic Link, Clic Tap. "
                        "No propongas selectores CSS."
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
            parsed_payload = parsed.model_dump()
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
    images, image_source = _image_paths(context)
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
