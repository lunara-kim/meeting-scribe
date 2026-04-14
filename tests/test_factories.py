"""get_stt / get_llm / get_publisher / get_trigger의 provider 라우팅 테스트."""
import os
import pytest

from stt import get_stt
from llm import get_llm
from publisher import get_publisher
from trigger import get_trigger


@pytest.fixture(autouse=True)
def _dummy_env(monkeypatch):
    # ${VAR} 치환 실패로 인한 SDK 초기화 오류 방지
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("NOTION_API_TOKEN", "test-token")
    monkeypatch.setenv("ATLASSIAN_API_TOKEN", "test-token")
    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-test")
    monkeypatch.setenv("SLACK_APP_TOKEN", "xapp-test")


def test_get_stt_unknown_provider_raises():
    with pytest.raises(ValueError, match="알 수 없는 STT"):
        get_stt({"stt": {"provider": "nope"}})


def test_get_llm_unknown_provider_raises():
    with pytest.raises(ValueError, match="알 수 없는 LLM"):
        get_llm({"llm": {"provider": "nope"}})


def test_get_publisher_unknown_provider_raises():
    with pytest.raises(ValueError, match="알 수 없는 publisher"):
        get_publisher({"publisher": {"provider": "nope"}})


def test_get_trigger_unknown_provider_raises():
    with pytest.raises(ValueError, match="알 수 없는 trigger"):
        get_trigger({"trigger": {"provider": "nope"}}, lambda e: None)


def test_get_stt_whisper_api():
    from stt.whisper_api import WhisperAPI
    inst = get_stt({"stt": {"provider": "whisper_api", "whisper_api": {"api_key": "${OPENAI_API_KEY}"}}})
    assert isinstance(inst, WhisperAPI)


def test_get_llm_anthropic():
    from llm.anthropic_llm import AnthropicLLM
    inst = get_llm({
        "llm": {"provider": "anthropic", "anthropic": {"api_key": "${ANTHROPIC_API_KEY}", "model": "claude-sonnet-4-5"}}
    })
    assert isinstance(inst, AnthropicLLM)


def test_get_publisher_notion():
    from publisher.notion import NotionPublisher
    inst = get_publisher({
        "publisher": {"provider": "notion", "notion": {
            "parent_page_id": "pid", "api_token": "${NOTION_API_TOKEN}"
        }}
    })
    assert isinstance(inst, NotionPublisher)
