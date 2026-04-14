from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Callable


@dataclass
class AudioEvent:
    """트리거가 감지한 오디오 파일 한 건.

    메신저별 차이를 흡수한 공통 페이로드. main.py의 오케스트레이터는
    이 객체만 받아서 STT → LLM → Publish 파이프라인을 돌린다.
    """
    file_bytes: bytes
    filename: str
    reply: Callable[[str], None]  # 진행 상태/결과 메시지를 원본 대화로 회신


OnAudio = Callable[[AudioEvent], None]


class Trigger(ABC):
    """메신저/채널 트리거의 공통 인터페이스.

    구현체는 자기 채널에서 오디오 파일을 감지하면 `on_audio(AudioEvent)`를
    호출할 책임만 진다. 실행 모델(Socket Mode, HTTP 서버 등)은 구현체 자유.
    """

    def __init__(self, config: dict, on_audio: OnAudio):
        self.config = config
        self.on_audio = on_audio

    @abstractmethod
    def start(self) -> None:
        """블로킹 실행. 프로세스 종료 전까지 이벤트 루프를 유지한다."""
        raise NotImplementedError
