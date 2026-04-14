def get_llm(config: dict):
    provider = config["llm"]["provider"]

    if provider == "anthropic":
        from .anthropic_llm import AnthropicLLM
        return AnthropicLLM(config["llm"]["anthropic"])
    if provider == "ollama":
        from .ollama_llm import OllamaLLM
        return OllamaLLM(config["llm"]["ollama"])

    raise ValueError(f"알 수 없는 LLM provider: {provider}")
