"""WhisperAPI: 파일 오픈 + 호출 인자 + 반환 텍스트 테스트."""
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from stt.whisper_api import WhisperAPI


def _make_stt(monkeypatch):
    import stt.whisper_api as mod
    monkeypatch.setattr(mod, "OpenAI", MagicMock())
    return WhisperAPI({"api_key": "direct-key"})


def test_env_var_substitution(monkeypatch):
    monkeypatch.setenv("WHISPER_KEY", "resolved")
    import stt.whisper_api as mod
    captured = {}

    def fake_ctor(api_key):
        captured["api_key"] = api_key
        return MagicMock()

    monkeypatch.setattr(mod, "OpenAI", fake_ctor)
    WhisperAPI({"api_key": "${WHISPER_KEY}"})
    assert captured["api_key"] == "resolved"


def test_transcribe_reads_file_and_returns_text(monkeypatch, tmp_path):
    stt = _make_stt(monkeypatch)
    stt.client.audio.transcriptions.create = MagicMock(
        return_value=SimpleNamespace(text="안녕하세요 회의 시작합니다")
    )

    audio = tmp_path / "meeting.wav"
    audio.write_bytes(b"RIFF....fake wav content")

    result = stt.transcribe(str(audio))

    assert result == "안녕하세요 회의 시작합니다"
    call_kwargs = stt.client.audio.transcriptions.create.call_args.kwargs
    assert call_kwargs["model"] == "whisper-1"
    # 파일 객체가 넘어갔는지
    assert hasattr(call_kwargs["file"], "read")
