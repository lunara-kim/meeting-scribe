import os
import anthropic


class AnthropicLLM:
    def __init__(self, config: dict):
        api_key = config.get("api_key", "")
        if api_key.startswith("${"):
            api_key = os.getenv(api_key[2:-1], "")
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = config.get("model", "claude-sonnet-4-5")
        self.max_tokens = config.get("max_tokens", 4096)

    def complete(self, prompt: str) -> str:
        response = self.client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        text = ""
        for block in response.content:
            if hasattr(block, "text"):
                text += block.text
        return text
