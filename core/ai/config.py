import os
from dataclasses import dataclass

@dataclass
class AIConfig:
    enabled: bool = os.getenv("AI_ENABLED", "false").lower() == "true"
    provider: str = os.getenv("AI_PROVIDER", "openai")

    enable_image_parse: bool = os.getenv("AI_ENABLE_IMAGE_PARSE", "false").lower() == "true"
    enable_dom_explorer: bool = os.getenv("AI_ENABLE_DOM_EXPLORER", "false").lower() == "true"
    enable_selector_rerank: bool = os.getenv("AI_ENABLE_SELECTOR_RERANK", "false").lower() == "true"

    selector_rerank_only_on_ambiguity: bool = os.getenv("AI_SELECTOR_RERANK_ONLY_ON_AMBIGUITY", "true").lower() == "true"

    model_image: str = os.getenv("AI_MODEL_IMAGE", "gpt-5-mini")
    model_dom: str = os.getenv("AI_MODEL_DOM", "gpt-5-mini")
    model_selector: str = os.getenv("AI_MODEL_SELECTOR", "gpt-5-mini")

    image_detail: str = os.getenv("AI_IMAGE_DETAIL", "low")
    max_tokens_image: int = int(os.getenv("AI_MAX_OUTPUT_TOKENS_IMAGE", "700"))
    max_tokens_dom: int = int(os.getenv("AI_MAX_OUTPUT_TOKENS_DOM", "500"))
    max_tokens_selector: int = int(os.getenv("AI_MAX_OUTPUT_TOKENS_SELECTOR", "350"))

    cache_dir: str = os.getenv("AI_CACHE_DIR", ".cache/ai")