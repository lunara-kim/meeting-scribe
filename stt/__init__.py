from .whisper_local import WhisperLocal
from .whisper_api import WhisperAPI


def get_stt(config: dict):
    provider = config["stt"]["provider"]

    if provider == "whisper_local":
        return WhisperLocal(config["stt"]["whisper_local"])
    if provider == "whisper_api":
        return WhisperAPI(config["stt"]["whisper_api"])

    raise ValueError(f"알 수 없는 STT provider: {provider}")
