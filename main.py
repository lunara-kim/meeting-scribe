import logging
import os
import tempfile
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

import yaml
from dotenv import load_dotenv

from logging_config import setup_logging
from stt import get_stt
from publisher import get_publisher
from llm import get_llm
from trigger import AudioEvent, get_trigger

setup_logging()
logger = logging.getLogger(__name__)


# ── Fly.io 헬스체크용 미니 HTTP 서버 ───────────────────────
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, format, *args):
        pass  # 헬스체크 로그 무시


def start_health_server():
    server = HTTPServer(("0.0.0.0", 8080), HealthHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    logger.info("health check server started", extra={"port": 8080})


load_dotenv()

# ── 설정 로드 ──────────────────────────────────────────────
with open("config.yaml", encoding="utf-8") as f:
    config = yaml.safe_load(f)


# ── 회의록 생성 ────────────────────────────────────────────
def generate_minutes(transcript: str, template: str = "") -> tuple[str, str]:
    """회의록 제목과 HTML 본문을 생성하여 (title, body_html) 튜플로 반환한다."""
    llm = get_llm(config)

    template_section = (
        f"\n## 회의록 양식 (아래 구조를 그대로 따라 작성하세요)\n{template}\n"
        if template else
        "\n기본 형식(회의 일시, 참석자, 주요 안건 및 논의 내용, 결정 사항, Action Item)으로 작성하세요.\n"
    )

    prompt = f"""아래 회의 녹취록을 분석하여 회의록을 작성해주세요.

## 출력 형식
첫 줄에 제목만 출력하고, 그 다음 줄부터 HTML 본문을 출력하세요.
제목 형식: 회의록 - [날짜] [주제]
{template_section}
## 녹취록
{transcript}
"""

    text = llm.complete(prompt)

    lines = text.strip().split("\n", 1)
    title = lines[0].strip().removeprefix("#").strip()
    body_html = lines[1].strip() if len(lines) > 1 else ""

    return title, body_html


def generate_and_publish(transcript: str) -> str:
    publisher = get_publisher(config)
    template = publisher.get_template()
    title, body_html = generate_minutes(transcript, template)
    return publisher.publish(title, body_html)


# ── 트리거 → STT → LLM → Publish 오케스트레이션 ───────────
def on_audio(event: AudioEvent) -> None:
    """트리거가 오디오 파일을 감지했을 때 호출되는 콜백."""
    ext = os.path.splitext(event.filename)[1].lower() or ".bin"

    event.reply("🎙️ 녹음 파일 감지! 회의록 생성을 시작합니다...")

    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        tmp.write(event.file_bytes)
        tmp_path = tmp.name

    try:
        event.reply("📝 음성 → 텍스트 변환 중...")
        stt = get_stt(config)
        transcript = stt.transcribe(tmp_path)
        logger.info("stt completed", extra={"preview": transcript[:200], "length": len(transcript)})

        event.reply("🤖 회의록 작성 및 게시 중...")
        page_url = generate_and_publish(transcript)

        event.reply(f"✅ 회의록이 생성되었습니다!\n{page_url}")

    except Exception as e:
        logger.exception("pipeline failed", extra={"audio_filename": event.filename})
        event.reply(f"❌ 오류가 발생했습니다: {str(e)}")
        raise

    finally:
        os.unlink(tmp_path)


# ── 실행 ───────────────────────────────────────────────────
if __name__ == "__main__":
    start_health_server()

    trigger = get_trigger(config, on_audio)
    provider = config["trigger"]["provider"]
    logger.info("meeting-scribe started", extra={"trigger": provider})

    try:
        trigger.start()
    except Exception:
        logger.exception("trigger failed to start")
        exit(1)
