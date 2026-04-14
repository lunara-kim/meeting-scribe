import logging

import whisper

logger = logging.getLogger(__name__)


class WhisperLocal:
    def __init__(self, config: dict):
        model_size = config.get("model_size", "medium")
        logger.info("loading local whisper model", extra={"model_size": model_size})
        self.model = whisper.load_model(model_size)

    def transcribe(self, audio_path: str) -> str:
        logger.info("local whisper transcription started", extra={"audio_path": audio_path})
        result = self.model.transcribe(audio_path)
        return result["text"]
