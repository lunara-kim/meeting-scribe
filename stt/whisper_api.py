import os
from openai import OpenAI


class WhisperAPI:
    def __init__(self, config: dict):
        api_key = config.get("api_key", "")
        if api_key.startswith("${"):
            api_key = os.getenv(api_key[2:-1], "")
        self.client = OpenAI(api_key=api_key)

    def transcribe(self, audio_path: str) -> str:
        print(f"[STT] OpenAI Whisper API 변환 시작: {audio_path}")
        with open(audio_path, "rb") as f:
            result = self.client.audio.transcriptions.create(
                model="whisper-1",
                file=f,
            )
        return result.text
