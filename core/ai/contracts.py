"""Pydantic contracts for AI module outputs."""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


def _extract_variants(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]

    text = str(value).strip()
    if not text:
        return []
    match = re.search(r"\{\{(.+?)\}\}", text)
    if match:
        text = match.group(1)
    if "|" not in text:
        return [text]
    return [part.strip() for part in text.split("|") if part.strip()]


class Interaction(BaseModel):
    tipo_evento: str | None = None
    flujo: str | None = None
    ubicacion: str | None = None
    elemento: str | None = None
    element_variants: list[str] = Field(default_factory=list)
    titulo_card: str | None = None
    title_variants: list[str] = Field(default_factory=list)
    texto_referencia: str | None = None
    interaction_mode: Literal["single", "group"] | None = None
    group_context: str | None = None
    zone_hint: str | None = None
    value_extraction_strategy: str | None = None
    confidence: float | None = 0.0
    warning: str | None = None

    @field_validator("element_variants", "title_variants", mode="before")
    @classmethod
    def normalize_variants(cls, value: Any) -> list[str]:
        return _extract_variants(value)


class PlanExtraction(BaseModel):
    activo: str | None = None
    seccion: str | None = None
    interactions: list[Interaction] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class DomActionSuggestion(BaseModel):
    action: Literal["none", "scroll", "open_nav", "expand_tab", "expand_accordion", "advance_carousel"]
    target_text: str | None = None
    reason: str
    confidence: float


class SelectorDecision(BaseModel):
    selected_selector: str | None
    confidence: float
    reason: str
    rejects: list[str] = Field(default_factory=list)
    requires_human_review: bool = False
