import base64
import hashlib
import hmac
import logging
import os
import threading
import time
from typing import Optional

import jwt  # PyJWT (with cryptography)
import requests
from flask import Flask, abort, request

from .base import AudioEvent, OnAudio, Trigger

logger = logging.getLogger(__name__)


AUDIO_EXTENSIONS = {".mp3", ".mp4", ".wav", ".m4a", ".ogg", ".webm", ".flac"}

AUTH_TOKEN_URL = "https://auth.worksmobile.com/oauth2/v2.0/token"
API_BASE = "https://www.worksapis.com/v1.0"


def _resolve(value: str) -> str:
    """`${ENV_VAR}` 형태면 환경변수로 치환한다."""
    if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
        return os.getenv(value[2:-1], "")
    return value


class NaverWorksTrigger(Trigger):
    """NAVER WORKS Bot Callback 기반 트리거.

    - Flask로 Callback URL을 제공 (예: POST /callback)
    - Service Account JWT → OAuth 2.0 Access Token 갱신
    - 오디오 첨부파일 이벤트 수신 시 파일 다운로드 후 on_audio 호출
    - 진행 상태/결과는 동일 채널에 메시지로 회신
    """

    def __init__(self, config: dict, on_audio: OnAudio):
        super().__init__(config, on_audio)

        self.client_id = _resolve(config["client_id"])
        self.client_secret = _resolve(config["client_secret"])
        self.service_account = _resolve(config["service_account"])
        self.bot_id = _resolve(config["bot_id"])
        self.bot_secret = _resolve(config["bot_secret"])

        # 개인키: 문자열(환경변수) 우선, 없으면 파일 경로
        private_key = _resolve(config.get("private_key", ""))
        if not private_key:
            path = config.get("private_key_path", "")
            if path and os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    private_key = f.read()
        if not private_key:
            raise RuntimeError(
                "NAVER WORKS private_key가 비어 있습니다 "
                "(NAVERWORKS_PRIVATE_KEY 또는 private_key_path 확인)."
            )
        self.private_key = private_key

        self.host = config.get("callback_host", "0.0.0.0")
        self.port = int(config.get("callback_port", 3000))
        self.callback_path = config.get("callback_path", "/callback")

        required = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "service_account": self.service_account,
            "bot_id": self.bot_id,
            "bot_secret": self.bot_secret,
        }
        missing = [k for k, v in required.items() if not v]
        if missing:
            raise RuntimeError(f"NAVER WORKS 설정 누락: {', '.join(missing)}")

        self._access_token: Optional[str] = None
        self._token_expires_at: float = 0.0
        self._token_lock = threading.Lock()

        self.flask_app = Flask(__name__)
        self._register_routes()

    # ── 토큰 관리 ────────────────────────────────────────
    def _build_jwt(self) -> str:
        now = int(time.time())
        payload = {
            "iss": self.client_id,
            "sub": self.service_account,
            "iat": now,
            "exp": now + 3600,
        }
        return jwt.encode(payload, self.private_key, algorithm="RS256")

    def _refresh_access_token(self) -> str:
        assertion = self._build_jwt()
        resp = requests.post(
            AUTH_TOKEN_URL,
            data={
                "assertion": assertion,
                "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "scope": "bot",
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

        token = data["access_token"]
        # 만료 1분 전 선제 갱신
        expires_in = int(data.get("expires_in", 86400))
        self._access_token = token
        self._token_expires_at = time.time() + expires_in - 60
        return token

    def _access_token_get(self) -> str:
        with self._token_lock:
            if not self._access_token or time.time() >= self._token_expires_at:
                return self._refresh_access_token()
            return self._access_token

    def _auth_headers(self) -> dict:
        return {"Authorization": f"Bearer {self._access_token_get()}"}

    # ── 서명 검증 ────────────────────────────────────────
    def _verify_signature(self, raw_body: bytes, signature: Optional[str]) -> bool:
        if not signature:
            return False
        mac = hmac.new(self.bot_secret.encode("utf-8"), raw_body, hashlib.sha256).digest()
        expected = base64.b64encode(mac).decode("utf-8")
        return hmac.compare_digest(expected, signature)

    # ── 파일/메시지 API ─────────────────────────────────
    def _download_attachment(self, file_id: str) -> bytes:
        """Bot 첨부파일 API로 바이너리를 받아온다.

        공식 흐름: GET /bots/{botId}/attachments/{fileId} → 다운로드 URL(302)
        requests가 follow_redirects 기본값이므로 최종 바이너리를 바로 받는다.
        """
        url = f"{API_BASE}/bots/{self.bot_id}/attachments/{file_id}"
        resp = requests.get(url, headers=self._auth_headers(), timeout=120, allow_redirects=True)
        resp.raise_for_status()
        return resp.content

    def _send_message(self, channel_id: str, text: str) -> None:
        url = f"{API_BASE}/bots/{self.bot_id}/channels/{channel_id}/messages"
        headers = {**self._auth_headers(), "Content-Type": "application/json"}
        payload = {"content": {"type": "text", "text": text}}
        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=30)
            resp.raise_for_status()
        except requests.RequestException:
            logger.exception("naverworks message send failed", extra={"channel_id": channel_id})

    # ── 이벤트 처리 ──────────────────────────────────────
    def _handle_event(self, payload: dict) -> None:
        """Callback 페이로드에서 오디오 파일을 추출해 on_audio 호출.

        빠른 응답을 위해 Flask 핸들러는 이 메서드를 백그라운드 스레드에서 호출한다.
        """
        if payload.get("type") != "message":
            return

        source = payload.get("source") or {}
        channel_id = source.get("channelId")
        content = payload.get("content") or {}
        content_type = content.get("type")

        if content_type != "file" or not channel_id:
            return

        filename = content.get("fileName") or ""
        ext = os.path.splitext(filename)[1].lower()
        if ext not in AUDIO_EXTENSIONS:
            return

        file_id = content.get("fileId")
        if not file_id:
            logger.warning("naverworks file event missing fileId")
            return

        def reply(text: str) -> None:
            self._send_message(channel_id, text)

        try:
            file_bytes = self._download_attachment(file_id)
        except requests.RequestException as e:
            reply(f"❌ 첨부파일 다운로드 실패: {e}")
            return

        self.on_audio(AudioEvent(file_bytes=file_bytes, filename=filename, reply=reply))

    # ── Flask 라우팅 ────────────────────────────────────
    def _register_routes(self):
        app = self.flask_app

        @app.post(self.callback_path)
        def callback():
            raw = request.get_data()
            signature = request.headers.get("X-WORKS-Signature")
            if not self._verify_signature(raw, signature):
                abort(401)

            payload = request.get_json(silent=True) or {}

            # 처리 시간이 길 수 있으니 백그라운드로 넘기고 즉시 200 응답
            threading.Thread(
                target=self._handle_event,
                args=(payload,),
                daemon=True,
            ).start()
            return "", 200

    # ── 실행 ──────────────────────────────────────────────
    def start(self) -> None:
        # 기동 시 한 번 토큰 발급해 설정/개인키 이상을 빠르게 노출
        try:
            self._refresh_access_token()
            logger.info("naverworks access token issued")
        except requests.RequestException:
            logger.warning("initial naverworks access token issuance failed; will retry on demand", exc_info=True)

        logger.info(
            "naverworks callback listener started",
            extra={"host": self.host, "port": self.port, "path": self.callback_path},
        )
        # 내부 서비스 용도이므로 Flask 내장 서버로 충분. 프로덕션에서는 gunicorn 앞에 둘 것.
        self.flask_app.run(host=self.host, port=self.port, use_reloader=False)
