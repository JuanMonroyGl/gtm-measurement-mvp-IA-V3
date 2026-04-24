"""OpenAI provider for image_parse.

This module is intentionally bounded: it extracts structured hints from plan text and images.
It does not propose selectors and does not alter final grounding rules.
"""

from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
from typing import Any

from core.ai.cache import AICache
from core.ai.config import AIConfig
from core.ai.contracts import PlanExtraction
from core.ai.openai_client import get_openai_client


FORBIDDEN_SELECTOR_FIELDS = {
    "selector_candidato",
    "selector_item",
    "selector_contenedor",
    "selector_activador",
}
PROMPT_VERSION = "image_parse_text_first_group_variants_v3"
TEXT_CONTEXT_LIMIT = 45000


def _to_data_url(path: Path) -> str:
    mime = "image/png"
    if path.suffix.lower() in {".jpg", ".jpeg"}:
        mime = "image/jpeg"
    elif path.suffix.lower() == ".webp":
        mime = "image/webp"
    encoded = base64.b64encode(path.read_bytes()).decode("utf-8")
    return f"data:{mime};base64,{encoded}"


def _parse_json_object(raw_text: str) -> tuple[dict[str, Any], list[str]]:
    warnings: list[str] = []
    text = (raw_text or "").strip()
    if not text:
        return {"activo": None, "seccion": None, "interactions": []}, ["OpenAI devolvio respuesta vacia."]

    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].strip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            try:
                parsed = json.loads(text[start : end + 1])
                warnings.append("OpenAI devolvio texto alrededor del JSON; se extrajo el objeto JSON.")
            except json.JSONDecodeError:
                return {"activo": None, "seccion": None, "interactions": []}, [
                    "JSON invalido devuelto por OpenAI image_parse."
                ]
        else:
            return {"activo": None, "seccion": None, "interactions": []}, [
                "JSON invalido devuelto por OpenAI image_parse."
            ]

    if not isinstance(parsed, dict):
        return {"activo": None, "seccion": None, "interactions": []}, [
            "OpenAI image_parse no devolvio un objeto JSON."
        ]

    return parsed, warnings


def _strip_selector_fields(parsed: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    warnings: list[str] = []
    interactions = parsed.get("interactions") or []
    if not isinstance(interactions, list):
        parsed["interactions"] = []
        return parsed, ["OpenAI image_parse devolvio interactions con formato invalido."]

    cleaned_interactions = []
    for item in interactions:
        if not isinstance(item, dict):
            continue
        forbidden = sorted(FORBIDDEN_SELECTOR_FIELDS & set(item.keys()))
        if forbidden:
            warnings.append(
                "OpenAI image_parse devolvio campos de selector prohibidos y fueron descartados: "
                + ", ".join(forbidden)
            )
        cleaned_interactions.append({key: value for key, value in item.items() if key not in FORBIDDEN_SELECTOR_FIELDS})

    parsed["interactions"] = cleaned_interactions
    return parsed, warnings


def _text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _entry_label(entry: dict[str, Any], fallback: str) -> str:
    kind = entry.get("kind") or fallback
    index = entry.get("index")
    source = entry.get("source")
    parts = [str(kind)]
    if index is not None:
        parts.append(f"index={index}")
    if source:
        parts.append(f"source={source}")
    return " | ".join(parts)


def _format_native_text_entries(native_text_entries: list[dict[str, Any]] | None) -> str:
    sections = []
    for entry in native_text_entries or []:
        text = str(entry.get("text") or "").strip()
        if not text:
            continue
        sections.append(f"[{_entry_label(entry, 'native_text')}]\n{text}")
    return "\n\n".join(sections)


def _format_image_evidence(image_evidence: list[dict[str, Any]] | None) -> str:
    sections = []
    for index, entry in enumerate(image_evidence or [], start=1):
        text = str(entry.get("extracted_text") or "").strip()
        if not text:
            lines = entry.get("extracted_lines") or []
            text = "\n".join(str(line) for line in lines if str(line).strip()).strip()
        if not text:
            continue
        label = entry.get("image_path") or entry.get("source") or f"image_evidence_{index}"
        method = entry.get("extraction_method")
        confidence = entry.get("confidence")
        metadata = [f"source={label}"]
        if method:
            metadata.append(f"method={method}")
        if confidence is not None:
            metadata.append(f"confidence={confidence}")
        sections.append(f"[{' | '.join(metadata)}]\n{text}")
    return "\n\n".join(sections)


def _build_text_context(
    *,
    native_text_entries: list[dict[str, Any]] | None,
    image_evidence: list[dict[str, Any]] | None,
    text_context: str | None,
) -> tuple[str, dict[str, Any]]:
    blocks = []
    native_text = _format_native_text_entries(native_text_entries)
    evidence_text = _format_image_evidence(image_evidence)
    extra_text = (text_context or "").strip()

    if native_text:
        blocks.append("Texto extraido del plan (PDF/PPTX):\n" + native_text)
    if evidence_text:
        blocks.append("Texto extraido de OCR/image_evidence:\n" + evidence_text)
    if extra_text:
        blocks.append("Contexto textual adicional:\n" + extra_text)

    full_text = "\n\n---\n\n".join(blocks)
    if len(full_text) > TEXT_CONTEXT_LIMIT:
        full_text = full_text[:TEXT_CONTEXT_LIMIT]

    metadata = {
        "used_native_text": bool(native_text),
        "used_image_evidence": bool(evidence_text),
        "text_context_chars": len(full_text),
        "native_text_chars": len(native_text),
        "image_evidence_chars": len(evidence_text),
        "native_text_hash": _text_hash(native_text) if native_text else None,
        "image_evidence_hash": _text_hash(evidence_text) if evidence_text else None,
    }
    return full_text, metadata


class OpenAIImageParseProvider:
    def __init__(self, config: AIConfig) -> None:
        self.config = config
        self.client = get_openai_client()
        self.cache = AICache(config.cache_dir)

    def _build_messages(self, image_paths: list[Path], plan_text_context: str) -> list[dict[str, Any]]:
        content: list[dict[str, Any]] = [
            {
                "type": "input_text",
                "text": (
                    "Extrae SOLO JSON válido con esta forma: "
                    "{activo, seccion, interactions:[{tipo_evento, flujo, ubicacion, elemento, element_variants, titulo_card, title_variants, interaction_mode, group_context, zone_hint, value_extraction_strategy, texto_referencia, confidence, warning}], warnings}. "
                    "Reglas: no inventar campos faltantes; usar null cuando falte evidencia; "
                    "Prioriza el texto extraido del plan cuando exista; usa imagenes solo como respaldo visual o para resolver dudas. "
                    "tipo_evento permitido: Clic Menu|Clic Tab|Clic Card|Clic Boton|Clic Link|Clic Tap. "
                    "interaction_mode solo puede ser single o group. "
                    "IMPORTANTE: conserva el tipo_evento exacto observado cuando coincida con la lista permitida. "
                    "Devuelve por interaccion: tipo_evento, flujo, ubicacion, elemento, element_variants, titulo_card, title_variants, interaction_mode, group_context, zone_hint, value_extraction_strategy, texto_referencia, confidence, warning. "
                    "Detecta variantes dentro de {{a|b|c}} o textos separados por pipes; por ejemplo elemento='{{inicio|necesidades|productos y servicios|educacion financiera}}' produce element_variants=['inicio','necesidades','productos y servicios','educacion financiera']. "
                    "Si existe titulo card, titulo de card o equivalente, copia ese texto en titulo_card y extrae title_variants con la misma regla de variantes. "
                    "Si una interaccion representa varias opciones del mismo patron, usa interaction_mode='group'. "
                    "Usa value_extraction_strategy='prefer_title_variant_then_click_text' para cards grupales con title_variants, 'match_element_variant_from_clicked_text' para grupos sin titulo de card, y 'click_text' para single. "
                    "No incluyas selector_candidato, selector_item, selector_contenedor ni selector_activador. "
                    "La IA puede clasificar interaction_mode, group_context y zone_hint, pero NO proponer selectores."
                ),
            }
        ]
        if plan_text_context:
            content.append(
                {
                    "type": "input_text",
                    "text": "Texto extraido del plan:\n" + plan_text_context,
                }
            )

        for image_path in image_paths:
            content.append(
                {
                    "type": "input_image",
                    "image_url": _to_data_url(image_path),
                    "detail": self.config.image_detail,
                }
            )

        return [{"role": "user", "content": content}]

    def parse(
        self,
        *,
        case_id: str,
        image_paths: list[Path],
        native_text_entries: list[dict[str, Any]] | None = None,
        image_evidence: list[dict[str, Any]] | None = None,
        text_context: str | None = None,
    ) -> dict:
        plan_text_context, context_metadata = _build_text_context(
            native_text_entries=native_text_entries,
            image_evidence=image_evidence,
            text_context=text_context,
        )
        input_modalities = []
        if context_metadata["used_native_text"]:
            input_modalities.append("native_text")
        if context_metadata["used_image_evidence"]:
            input_modalities.append("image_evidence")
        if image_paths:
            input_modalities.append("images")

        request_fingerprint = {
            "provider": "openai",
            "prompt_version": PROMPT_VERSION,
            "model": self.config.model_image,
            "image_detail": self.config.image_detail,
            "native_text_hash": context_metadata["native_text_hash"],
            "native_text_chars": context_metadata["native_text_chars"],
            "image_evidence_hash": context_metadata["image_evidence_hash"],
            "image_evidence_chars": context_metadata["image_evidence_chars"],
            "text_context_hash": _text_hash(text_context or "") if text_context else None,
            "text_context_chars": len(text_context or ""),
            "paths": [str(p) for p in image_paths],
            "sizes": [p.stat().st_size for p in image_paths],
        }
        cache_key = self.cache.build_key(request_fingerprint)
        cached = self.cache.read("image_parse", cache_key)
        if cached:
            cached["cache_hit"] = True
            return cached

        messages = self._build_messages(image_paths, plan_text_context)
        response = self.client.responses.create(
            model=self.config.model_image,
            input=messages,
            max_output_tokens=self.config.max_tokens_image,
        )

        raw_text = response.output_text or "{}"
        parsed, warnings = _parse_json_object(raw_text)
        parsed, selector_warnings = _strip_selector_fields(parsed)
        warnings.extend(selector_warnings)
        if raw_text.strip() == "{}":
            warnings.append("AI image_parse devolvio '{}'; se conserva pipeline deterministico.")
        if not parsed.get("interactions"):
            warnings.append("AI image_parse no extrajo interacciones; se conserva pipeline deterministico.")
        existing_warnings = parsed.get("warnings") if isinstance(parsed.get("warnings"), list) else []
        parsed["warnings"] = list(dict.fromkeys([*existing_warnings, *warnings]))

        contract = PlanExtraction.model_validate(parsed)
        payload = {
            "provider": "openai",
            "enabled": True,
            "cache_hit": False,
            "case_id": case_id,
            "model": self.config.model_image,
            "prompt_version": PROMPT_VERSION,
            "used_native_text": context_metadata["used_native_text"],
            "used_image_evidence": context_metadata["used_image_evidence"],
            "used_images": bool(image_paths),
            "text_context_chars": context_metadata["text_context_chars"],
            "input_modalities": input_modalities,
            "image_count": len(image_paths),
            "parsed": contract.model_dump(),
            "raw_text": raw_text,
            "warnings": contract.warnings,
        }
        self.cache.write("image_parse", cache_key, payload)
        return payload
