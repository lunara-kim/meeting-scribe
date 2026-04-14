import os
import time

import requests
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from .base import AudioEvent, OnAudio, Trigger


AUDIO_EXTENSIONS = {".mp3", ".mp4", ".wav", ".m4a", ".ogg", ".webm", ".flac"}


def _resolve(value: str) -> str:
    """`${ENV_VAR}` 형태면 환경변수로 치환한다."""
    if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
        return os.getenv(value[2:-1], "")
    return value


class SlackTrigger(Trigger):
    """Slack Bolt + Socket Mode 기반 트리거.

    - `app_mention`: 스레드 내 오디오 파일 탐색 후 처리
    - `file_shared`: 오디오 확장자면 즉시 처리
    """

    def __init__(self, config: dict, on_audio: OnAudio):
        super().__init__(config, on_audio)
        self.bot_token = _resolve(config["bot_token"])
        self.app_token = _resolve(config["app_token"])

        if not self.bot_token:
            raise RuntimeError("Slack bot_token이 비어 있습니다 (SLACK_BOT_TOKEN 확인).")
        if not self.app_token:
            raise RuntimeError("Slack app_token이 비어 있습니다 (SLACK_APP_TOKEN 확인).")
        if not self.app_token.startswith("xapp-"):
            print(f"⚠️ SLACK_APP_TOKEN이 'xapp-'으로 시작하지 않습니다: {self.app_token[:10]}...")

        self.app = App(token=self.bot_token)
        self._register_handlers()

    # ── 내부 ──────────────────────────────────────────────
    def _download_file(self, client, file_id: str, expected_size: int = 0, max_attempts: int = 5) -> bytes:
        """Slack 파일을 다운로드하되, 처리가 덜 끝난 경우를 대비해 재시도한다.

        Slack의 file_shared 이벤트는 업로드 처리 완료 전에 발생할 수 있어
        최초 다운로드가 0바이트를 반환하는 경우가 있다.
        """
        headers = {"Authorization": f"Bearer {self.bot_token}"}
        last_error = None

        for attempt in range(1, max_attempts + 1):
            info = client.files_info(file=file_id)["file"]
            size = info.get("size", 0)
            url = info.get("url_private_download") or info.get("url_private")

            if size == 0 or not url:
                print(f"[DOWNLOAD] attempt {attempt}: 파일 처리 대기 중 (size={size})")
                time.sleep(2 * attempt)
                continue

            try:
                resp = requests.get(url, headers=headers, timeout=60)
                resp.raise_for_status()
                content = resp.content

                if len(content) == 0:
                    print(f"[DOWNLOAD] attempt {attempt}: 0바이트 응답, 재시도")
                    time.sleep(2 * attempt)
                    continue

                if expected_size and len(content) < expected_size * 0.9:
                    print(f"[DOWNLOAD] attempt {attempt}: 불완전한 다운로드 ({len(content)}/{expected_size}), 재시도")
                    time.sleep(2 * attempt)
                    continue

                print(f"[DOWNLOAD] 성공: {len(content)} bytes (attempt {attempt})")
                return content

            except requests.RequestException as e:
                last_error = e
                print(f"[DOWNLOAD] attempt {attempt} 실패: {e}")
                time.sleep(2 * attempt)

        raise RuntimeError(f"파일 다운로드 {max_attempts}회 실패: {last_error}")

    def _dispatch(self, file_info: dict, client, channel: str, thread_ts):
        """파일을 내려받아 AudioEvent를 on_audio에 넘긴다."""
        filename = file_info.get("name", "")
        file_id = file_info["id"]
        expected_size = file_info.get("size", 0)

        def reply(text: str) -> None:
            client.chat_postMessage(channel=channel, text=text, thread_ts=thread_ts)

        content = self._download_file(client, file_id, expected_size)
        self.on_audio(AudioEvent(file_bytes=content, filename=filename, reply=reply))

    # ── 이벤트 핸들러 등록 ────────────────────────────────
    def _register_handlers(self):
        app = self.app

        @app.event("app_mention")
        def on_mention(event, client, say):
            """@meeting-scribe 멘션 시 → 같은 스레드의 오디오 파일 처리"""
            channel = event["channel"]
            thread_ts = event.get("thread_ts") or event.get("ts")

            result = client.conversations_replies(channel=channel, ts=thread_ts)
            messages = result.get("messages", [])

            audio_file = None
            for msg in messages:
                for f in msg.get("files", []):
                    ext = os.path.splitext(f.get("name", ""))[1].lower()
                    if ext in AUDIO_EXTENSIONS:
                        audio_file = f
                        break
                if audio_file:
                    break

            if not audio_file:
                say(text="⚠️ 스레드에서 오디오 파일을 찾지 못했습니다. 녹음 파일과 같은 스레드에서 멘션해 주세요.", thread_ts=thread_ts)
                return

            self._dispatch(audio_file, client, channel, thread_ts)

        @app.event("file_shared")
        def on_file_shared(event, client, say):
            file_id = event["file_id"]
            file_info = client.files_info(file=file_id)["file"]
            filename = file_info.get("name", "")
            ext = os.path.splitext(filename)[1].lower()

            if ext not in AUDIO_EXTENSIONS:
                return

            channels = file_info.get("channels", [])
            if not channels:
                print(f"[WARN] file_shared 이벤트에 채널 정보 없음: {file_id}")
                return

            channel = channels[0]
            thread_ts = (
                file_info.get("shares", {}).get("public", {}).get(channel, [{}])[0].get("ts")
            )

            self._dispatch(file_info, client, channel, thread_ts)

    # ── 실행 ──────────────────────────────────────────────
    def start(self) -> None:
        print("🔌 Slack Socket Mode 연결 시도 중...")
        handler = SocketModeHandler(self.app, self.app_token)
        handler.start()
