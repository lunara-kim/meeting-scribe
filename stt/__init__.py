def get_stt(config: dict):
    provider = config["stt"]["provider"]

    if provider == "whisper_local":
        from .whisper_local import WhisperLocal
        return WhisperLocal(config["stt"]["whisper_local"])
    if provider == "whisper_api":
        from .whisper_api import WhisperAPI
        return WhisperAPI(config["stt"]["whisper_api"])

    raise ValueError(f"알 수 없는 STT provider: {provider}")
