from __future__ import annotations

import json
from typing import Any

from openai import OpenAIError
from pydantic import BaseModel, Field

from core.ai.cache import AICache
from core.ai.config import AIConfig
from core.ai.openai_client import get_openai_client
from core.ai.selector_rerank.base import SelectorRerankProvider


PROMPT_VERSION = "selector_rerank_closed_candidates_v1"
TEXT_LIMIT = 900
LIST_LIMIT = 25


class SelectorReject(BaseModel):
    selector: str | None = None
    reason: str | None = None


class SelectorDecision(BaseModel):
    selected_selector: str | None = None
    selected_container_selector: str | None = None
    selected_item_selector: str | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    reason: str = ""
    rejects: list[SelectorReject] = Field(default_factory=list)
    requires_human_review: bool = True


def _truncate(value: Any, limit: int = TEXT_LIMIT) -> Any:
    if isinstance(value, str):
        clean = value.replace("data:image/", "data-image-redacted:")
        return clean[:limit]
    if isinstance(value, list):
        return [_truncate(item, limit) for item in value[:LIST_LIMIT]]
    if isinstance(value, dict):
        return {str(key): _truncate(item, limit) for key, item in value.items()}
    return value


def _parse_json_object(raw_text: str) -> tuple[dict[str, Any], list[str]]:
    warnings: list[str] = []
    text = (raw_text or "").strip()
    if not text:
        return {}, ["OpenAI selector_rerank devolvio respuesta vacia."]

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
                return {}, ["JSON invalido devuelto por OpenAI selector_rerank."]
        else:
            return {}, ["JSON invalido devuelto por OpenAI selector_rerank."]

    if not isinstance(parsed, dict):
        return {}, ["OpenAI selector_rerank no devolvio un objeto JSON."]
    return parsed, warnings


def _safe_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "selector",
        "selector_source",
        "selector_origin",
        "selector_item",
        "selector_contenedor",
        "match_count",
        "container_match_count",
        "variant_coverage",
        "minimum_variant_coverage",
        "visible_text",
        "outer_html_excerpt",
        "promotion_blockers",
        "safety_blockers",
        "source",
        "origin",
        "card_mapping",
        "matched_variants",
        "group_item_count",
        "candidate_group_item_count",
        "exists_in_dom",
        "closest_runtime_supported",
        "click_grounded",
    }
    return {key: _truncate(candidate.get(key)) for key in allowed if key in candidate}


def _sanitize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    candidates = [_safe_candidate(item) for item in payload.get("candidates_considered") or []]
    rejected = [_safe_candidate(item) for item in payload.get("rejected_candidates") or []]
    return {
        "case_id": payload.get("case_id"),
        "interaction_index": payload.get("interaction_index"),
        "tipo_evento": payload.get("tipo_evento"),
        "flujo": payload.get("flujo"),
        "ubicacion": payload.get("ubicacion"),
        "group_context": payload.get("group_context"),
        "zone_hint": payload.get("zone_hint"),
        "element_variants": _truncate(payload.get("element_variants") or []),
        "title_variants": _truncate(payload.get("title_variants") or []),
        "allowed_selectors": _truncate(payload.get("allowed_selectors") or []),
        "candidates_considered": candidates[:LIST_LIMIT],
        "rejected_candidates": rejected[:LIST_LIMIT],
    }


def _normalize_result(parsed: dict[str, Any], warnings: list[str], *, model: str, cache_hit: bool) -> dict[str, Any]:
    rejects = parsed.get("rejects") if isinstance(parsed.get("rejects"), list) else []
    confidence = parsed.get("confidence")
    try:
        confidence_value = float(confidence)
    except (TypeError, ValueError):
        confidence_value = 0.0
        warnings.append("OpenAI selector_rerank devolvio confidence invalida; se usa 0.0.")

    return {
        "provider": "openai",
        "enabled": True,
        "model": model,
        "cache_hit": cache_hit,
        "selected_selector": parsed.get("selected_selector"),
        "selected_container_selector": parsed.get("selected_container_selector"),
        "selected_item_selector": parsed.get("selected_item_selector"),
        "confidence": max(0.0, min(1.0, confidence_value)),
        "reason": parsed.get("reason") if isinstance(parsed.get("reason"), str) else "",
        "rejects": [
            {
                "selector": item.get("selector"),
                "reason": item.get("reason"),
            }
            for item in rejects
            if isinstance(item, dict)
        ],
        "requires_human_review": bool(parsed.get("requires_human_review", True)),
        "warnings": warnings,
    }


def _response_status_warning(response: Any, prefix: str) -> str:
    status = getattr(response, "status", None)
    incomplete_details = getattr(response, "incomplete_details", None)
    return f"{prefix}: status={status} incomplete_details={incomplete_details}"


class OpenAISelectorRerankProvider(SelectorRerankProvider):
    def __init__(self, config: AIConfig) -> None:
        self.config = config
        self.cache = AICache(config.cache_dir)
        self._client = None

    @property
    def client(self):
        if self._client is None:
            self._client = get_openai_client()
        return self._client

    def _build_messages(self, sanitized_payload: dict[str, Any]) -> list[dict[str, str]]:
        return [
            {
                "role": "system",
                "content": (
                    "Eres un reranker de selectores CSS para un pipeline GTM. "
                    "Solo puedes elegir selectores que existan literalmente en allowed_selectors o en candidates_considered. "
                    "No inventes selectores, no compongas selectores nuevos y no selecciones raw_html_fallback. "
                    "Si hay safety_blockers, selector generico, match_count irrazonable o falta evidencia, exige revision humana."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Elige, si procede, un candidato existente para resolver esta interaccion. "
                    "Devuelve una decision SelectorDecision. Payload cerrado:\n"
                    + json.dumps(sanitized_payload, ensure_ascii=False, indent=2)
                ),
            },
        ]

    def _call_model(self, sanitized_payload: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
        messages = self._build_messages(sanitized_payload)
        warnings: list[str] = []
        try:
            response = self.client.responses.parse(
                model=self.config.model_selector,
                input=messages,
                text_format=SelectorDecision,
                max_output_tokens=self.config.max_tokens_selector,
                reasoning={"effort": "minimal"},
            )
            parsed = response.output_parsed
            if parsed is not None:
                return parsed.model_dump(), warnings
            warnings.append("OpenAI selector_rerank no devolvio SelectorDecision parseable.")
            warnings.append(_response_status_warning(response, "Structured Outputs vacio"))
        except (AttributeError, TypeError, OpenAIError) as exc:
            warnings.append(
                "Structured Outputs via Responses API no disponible o rechazado; "
                f"se usa fallback JSON estricto. Detalle: {exc}"
            )

        fallback_messages = [
            messages[0],
            {
                "role": "user",
                "content": (
                    messages[1]["content"]
                    + "\nDevuelve solo JSON valido con esta forma exacta: "
                    '{"selected_selector": "...", "selected_container_selector": "...", '
                    '"selected_item_selector": "...", "confidence": 0.0, "reason": "...", '
                    '"rejects": [{"selector": "...", "reason": "..."}], '
                    '"requires_human_review": true}.'
                ),
            },
        ]
        response = self.client.responses.create(
            model=self.config.model_selector,
            input=fallback_messages,
            max_output_tokens=self.config.max_tokens_selector,
            reasoning={"effort": "minimal"},
        )
        parsed, parse_warnings = _parse_json_object(response.output_text or "")
        warnings.extend(parse_warnings)
        if not parsed:
            warnings.append(_response_status_warning(response, "Fallback JSON vacio"))
        return parsed, warnings

    def rerank(self, payload: dict) -> dict:
        sanitized_payload = _sanitize_payload(payload)
        request_fingerprint = {
            "provider": "openai",
            "prompt_version": PROMPT_VERSION,
            "model": self.config.model_selector,
            "payload": sanitized_payload,
        }
        cache_key = self.cache.build_key(request_fingerprint)
        cached = self.cache.read("selector_rerank", cache_key)
        if cached:
            cached["cache_hit"] = True
            return cached

        parsed, warnings = self._call_model(sanitized_payload)
        if not parsed:
            result = _normalize_result(
                {"requires_human_review": True, "reason": "Respuesta JSON invalida o vacia."},
                warnings,
                model=self.config.model_selector,
                cache_hit=False,
            )
        else:
            result = _normalize_result(parsed, warnings, model=self.config.model_selector, cache_hit=False)
        result["prompt_version"] = PROMPT_VERSION
        result["request_payload"] = sanitized_payload
        self.cache.write("selector_rerank", cache_key, result)
        return result
