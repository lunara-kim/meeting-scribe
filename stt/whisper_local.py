import whisper


class WhisperLocal:
    def __init__(self, config: dict):
        model_size = config.get("model_size", "medium")
        print(f"[STT] 로컬 Whisper 모델 로딩: {model_size}")
        self.model = whisper.load_model(model_size)

    def transcribe(self, audio_path: str) -> str:
        print(f"[STT] 변환 시작: {audio_path}")
        result = self.model.transcribe(audio_path)
        return result["text"]
