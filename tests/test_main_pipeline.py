"""골든 파이프라인 테스트.

고정된 transcript fixture를 입력으로 넣고, LLM/Publisher를 mock하여
title/body 파싱, 템플릿 주입, 호출 순서가 깨지지 않는지 검증한다.
실제 오디오/외부 API는 호출하지 않는다.
"""
from pathlib import Path
from unittest.mock import MagicMock

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def sample_transcript():
    return (FIXTURES / "transcript_sample.txt").read_text(encoding="utf-8")


@pytest.fixture
def main_module(monkeypatch):
    """main 모듈을 import. config.yaml은 프로젝트 루트의 실제 파일을 사용."""
    import main
    return main


def test_generate_minutes_parses_title_and_body(main_module, sample_transcript, monkeypatch):
    llm = MagicMock()
    llm.complete.return_value = "회의록 - 2026-04-14 v2 로드맵\n<h1>안건</h1><p>상세</p>"
    monkeypatch.setattr(main_module, "get_llm", lambda cfg: llm)

    title, body = main_module.generate_minutes(sample_transcript)

    assert title == "회의록 - 2026-04-14 v2 로드맵"
    assert body == "<h1>안건</h1><p>상세</p>"

    prompt = llm.complete.call_args.args[0]
    # 녹취록이 프롬프트에 포함돼야 한다
    assert "박철수" in prompt
    assert "meeting-scribe" in prompt
    # 템플릿 없을 때 기본 형식 안내가 포함돼야 한다
    assert "기본 형식" in prompt
    assert "Action Item" in prompt


def test_generate_minutes_strips_markdown_header_prefix(main_module, sample_transcript, monkeypatch):
    llm = MagicMock()
    llm.complete.return_value = "# 회의록 - 제목\n<p>body</p>"
    monkeypatch.setattr(main_module, "get_llm", lambda cfg: llm)

    title, body = main_module.generate_minutes(sample_transcript)
    assert title == "회의록 - 제목"
    assert body == "<p>body</p>"


def test_generate_minutes_injects_template(main_module, sample_transcript, monkeypatch):
    llm = MagicMock()
    llm.complete.return_value = "제목\n본문"
    monkeypatch.setattr(main_module, "get_llm", lambda cfg: llm)

    template = "## 참석자\n## 결정사항"
    main_module.generate_minutes(sample_transcript, template=template)

    prompt = llm.complete.call_args.args[0]
    assert "회의록 양식" in prompt
    assert template in prompt
    assert "기본 형식" not in prompt  # 템플릿 있을 땐 기본 안내가 들어가면 안 됨


def test_generate_minutes_handles_missing_body(main_module, sample_transcript, monkeypatch):
    llm = MagicMock()
    llm.complete.return_value = "제목만 있음"
    monkeypatch.setattr(main_module, "get_llm", lambda cfg: llm)

    title, body = main_module.generate_minutes(sample_transcript)
    assert title == "제목만 있음"
    assert body == ""


def test_generate_and_publish_uses_template_from_publisher(main_module, sample_transcript, monkeypatch):
    llm = MagicMock()
    llm.complete.return_value = "회의록 제목\n<p>body</p>"
    monkeypatch.setattr(main_module, "get_llm", lambda cfg: llm)

    publisher = MagicMock()
    publisher.get_template.return_value = "## 양식"
    publisher.publish.return_value = "https://example.com/page/1"
    monkeypatch.setattr(main_module, "get_publisher", lambda cfg: publisher)

    url = main_module.generate_and_publish(sample_transcript)

    assert url == "https://example.com/page/1"
    publisher.get_template.assert_called_once()
    publisher.publish.assert_called_once_with("회의록 제목", "<p>body</p>")
    # publisher 템플릿이 LLM 프롬프트에 주입됐는지
    prompt = llm.complete.call_args.args[0]
    assert "## 양식" in prompt


def test_on_audio_runs_full_pipeline(main_module, sample_transcript, monkeypatch, tmp_path):
    """골든 경로: trigger → STT → LLM → publish → reply 네 번"""
    from trigger import AudioEvent

    stt = MagicMock()
    stt.transcribe.return_value = sample_transcript
    monkeypatch.setattr(main_module, "get_stt", lambda cfg: stt)

    llm = MagicMock()
    llm.complete.return_value = "회의록 - 2026-04-14\n<p>본문</p>"
    monkeypatch.setattr(main_module, "get_llm", lambda cfg: llm)

    publisher = MagicMock()
    publisher.get_template.return_value = ""
    publisher.publish.return_value = "https://notion.so/page"
    monkeypatch.setattr(main_module, "get_publisher", lambda cfg: publisher)

    replies = []
    event = AudioEvent(
        file_bytes=b"fake audio bytes",
        filename="meeting.m4a",
        reply=replies.append,
    )

    main_module.on_audio(event)

    # reply 순서: 감지 → STT → 게시 → 완료
    assert len(replies) == 4
    assert "감지" in replies[0]
    assert "텍스트 변환" in replies[1]
    assert "게시" in replies[2]
    assert "https://notion.so/page" in replies[3]

    # STT는 실제 임시파일 경로로 호출됐고, 그 파일이 이미 정리됐는지 확인
    called_path = stt.transcribe.call_args.args[0]
    assert called_path.endswith(".m4a")
    assert not Path(called_path).exists()  # finally 블록에서 unlink됐어야 함

    publisher.publish.assert_called_once_with("회의록 - 2026-04-14", "<p>본문</p>")


def test_on_audio_reports_error_and_reraises(main_module, monkeypatch):
    from trigger import AudioEvent

    stt = MagicMock()
    stt.transcribe.side_effect = RuntimeError("whisper 폭발")
    monkeypatch.setattr(main_module, "get_stt", lambda cfg: stt)
    monkeypatch.setattr(main_module, "get_llm", lambda cfg: MagicMock())
    monkeypatch.setattr(main_module, "get_publisher", lambda cfg: MagicMock())

    replies = []
    event = AudioEvent(
        file_bytes=b"x",
        filename="a.wav",
        reply=replies.append,
    )

    with pytest.raises(RuntimeError, match="whisper 폭발"):
        main_module.on_audio(event)

    # 마지막 reply는 에러 메시지
    assert any("오류" in r for r in replies)
