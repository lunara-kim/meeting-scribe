import json
import logging
import os
import sys
from datetime import datetime, timezone


class JsonFormatter(logging.Formatter):
    """Fly.io 로그 수집기가 파싱하기 쉬운 한 줄 JSON 포맷."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)

        # logger.info(..., extra={"key": val}) 로 넘긴 필드는 LogRecord 속성으로 붙는다.
        reserved = set(logging.LogRecord("", 0, "", 0, "", None, None).__dict__) | {"message", "asctime"}
        for key, value in record.__dict__.items():
            if key not in reserved and not key.startswith("_"):
                payload[key] = value

        return json.dumps(payload, ensure_ascii=False, default=str)


def setup_logging() -> None:
    """루트 로거를 한 번만 설정한다. LOG_LEVEL / LOG_FORMAT 환경변수로 제어."""
    level = os.getenv("LOG_LEVEL", "INFO").upper()
    fmt = os.getenv("LOG_FORMAT", "json").lower()

    root = logging.getLogger()
    if getattr(root, "_meeting_scribe_configured", False):
        return

    for handler in list(root.handlers):
        root.removeHandler(handler)

    handler = logging.StreamHandler(sys.stdout)
    if fmt == "plain":
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    else:
        handler.setFormatter(JsonFormatter())

    root.addHandler(handler)
    root.setLevel(level)

    # 외부 라이브러리의 과한 DEBUG 로그 억제
    for noisy in ("urllib3", "slack_bolt", "slack_sdk", "werkzeug"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    root._meeting_scribe_configured = True
