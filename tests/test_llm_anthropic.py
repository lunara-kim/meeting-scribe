"""AnthropicLLM의 env 치환 / 응답 텍스트 추출 / 설정 기본값 테스트."""
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from llm.anthropic_llm import AnthropicLLM


def _make_llm(monkeypatch, config=None):
    # anthropic.Anthropic 생성자를 MagicMock으로 치환해 실제 SDK 초기화 회피
    import anthropic
    monkeypatch.setattr(anthropic, "Anthropic", MagicMock())
    cfg = config or {"api_key": "direct-key"}
    return AnthropicLLM(cfg)


def test_env_var_substitution(monkeypatch):
    monkeypatch.setenv("MY_KEY", "resolved-value")
    import anthropic
    captured = {}

    def fake_ctor(api_key):
        captured["api_key"] = api_key
        return MagicMock()

    monkeypatch.setattr(anthropic, "Anthropic", fake_ctor)
    AnthropicLLM({"api_key": "${MY_KEY}"})
    assert captured["api_key"] == "resolved-value"


def test_default_model_and_max_tokens(monkeypatch):
    llm = _make_llm(monkeypatch)
    assert llm.model == "claude-sonnet-4-5"
    assert llm.max_tokens == 4096


def test_custom_model_override(monkeypatch):
    llm = _make_llm(monkeypatch, {"api_key": "k", "model": "claude-opus-4-6", "max_tokens": 1024})
    assert llm.model == "claude-opus-4-6"
    assert llm.max_tokens == 1024


def test_complete_concatenates_text_blocks(monkeypatch):
    llm = _make_llm(monkeypatch)
    block1 = SimpleNamespace(text="Hello ")
    block2 = SimpleNamespace(text="world")
    non_text = object()  # text 속성 없음 → 무시돼야 함
    response = SimpleNamespace(content=[block1, non_text, block2])
    llm.client.messages.create = MagicMock(return_value=response)

    result = llm.complete("prompt")

    assert result == "Hello world"
    llm.client.messages.create.assert_called_once()
    call_kwargs = llm.client.messages.create.call_args.kwargs
    assert call_kwargs["model"] == "claude-sonnet-4-5"
    assert call_kwargs["max_tokens"] == 4096
    assert call_kwargs["messages"] == [{"role": "user", "content": "prompt"}]
