from .base import AudioEvent, OnAudio, Trigger


def get_trigger(config: dict, on_audio: OnAudio) -> Trigger:
    provider = config["trigger"]["provider"]

    if provider == "slack":
        from .slack import SlackTrigger
        return SlackTrigger(config["trigger"]["slack"], on_audio)
    if provider == "naverworks":
        from .naverworks import NaverWorksTrigger
        return NaverWorksTrigger(config["trigger"]["naverworks"], on_audio)

    raise ValueError(f"알 수 없는 trigger provider: {provider}")


__all__ = ["AudioEvent", "OnAudio", "Trigger", "get_trigger"]
