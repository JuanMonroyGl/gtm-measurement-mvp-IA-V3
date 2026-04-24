from __future__ import annotations

from dotenv import load_dotenv
from openai import OpenAI

from core.ai.config import AIConfig


def main() -> None:
    load_dotenv()
    config = AIConfig.from_env()
    client = OpenAI()
    response = client.responses.create(
        model=config.model_selector,
        input="Responde solo OK.",
        max_output_tokens=32,
    )
    if not getattr(response, "id", None):
        raise RuntimeError("OpenAI smoke no devolvio response id.")
    print("OpenAI smoke ok")


if __name__ == "__main__":
    main()
