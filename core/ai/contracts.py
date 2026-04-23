from typing import Optional, List, Literal
from pydantic import BaseModel

class Interaction(BaseModel):
    tipo_evento: str
    flujo: str
    ubicacion: str
    texto_referencia: str
    confidence: float
    warning: Optional[str] = None

class PlanExtraction(BaseModel):
    activo: str
    seccion: str
    interactions: List[Interaction]

class DomActionSuggestion(BaseModel):
    action: Literal["none", "scroll", "open_nav", "expand_tab", "expand_accordion", "advance_carousel"]
    target_text: Optional[str] = None
    reason: str
    confidence: float

class SelectorDecision(BaseModel):
    selected_selector: Optional[str]
    confidence: float
    reason: str
    rejects: List[str] = []
    requires_human_review: bool = False