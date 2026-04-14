import os
import tempfile
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

import yaml
import requests
import anthropic
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from dotenv import load_dotenv

from stt import get_stt
from publisher import get_publisher


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
    print("🩺 Health check server started on :8080")

load_dotenv()

# ── 설정 로드 ──────────────────────────────────────────────
with open("config.yaml") as f:
    config = yaml.safe_load(f)

# ── Slack 앱 초기화 ────────────────────────────────────────
app = App(token=os.getenv("SLACK_BOT_TOKEN"))

AUDIO_EXTENSIONS = {".mp3", ".mp4", ".wav", ".m4a", ".ogg", ".webm", ".flac"}


# ── Slack 이벤트 핸들러 ────────────────────────────────────
@app.event("app_mention")
def on_mention(event, client, say):
    """@meeting-scribe 멘션 시 → 같은 스레드(또는 채널)의 오디오 파일 처리"""
    channel = event["channel"]
    thread_ts = event.get("thread_ts") or event.get("ts")

    # 스레드 내 메시지 목록 조회
    result = client.conversations_replies(channel=channel, ts=thread_ts)
    messages = result.get("messages", [])

    # 오디오 파일 탐색
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

    _process_audio_file(audio_file, say, thread_ts)


def _process_audio_file(file_info, say, thread_ts):
    """오디오 파일을 다운로드 → STT → 회의록 생성 → Confluence 게시"""
    filename = file_info.get("name", "")
    ext = os.path.splitext(filename)[1].lower()

    say(text="🎙️ 녹음 파일 감지! 회의록 생성을 시작합니다...", thread_ts=thread_ts)

    response = requests.get(
        file_info["url_private_download"],
        headers={"Authorization": f"Bearer {os.getenv('SLACK_BOT_TOKEN')}"},
    )

    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        tmp.write(response.content)
        tmp_path = tmp.name

    try:
        say(text="📝 음성 → 텍스트 변환 중...", thread_ts=thread_ts)
        stt = get_stt(config)
        transcript = stt.transcribe(tmp_path)
        print(f"[STT 결과]\n{transcript[:200]}...")

        say(text="🤖 회의록 작성 및 게시 중...", thread_ts=thread_ts)
        page_url = generate_and_publish(transcript)

        say(text=f"✅ 회의록이 생성되었습니다!\n{page_url}", thread_ts=thread_ts)

    except Exception as e:
        say(text=f"❌ 오류가 발생했습니다: {str(e)}", thread_ts=thread_ts)
        raise

    finally:
        os.unlink(tmp_path)


@app.event("file_shared")
def on_file_shared(event, client, say):
    file_id = event["file_id"]
    file_info = client.files_info(file=file_id)["file"]
    filename = file_info.get("name", "")
    ext = os.path.splitext(filename)[1].lower()

    if ext not in AUDIO_EXTENSIONS:
        return  # 오디오 파일이 아니면 무시

    # file_shared 이벤트에서 채널 정보 추출
    channels = file_info.get("channels", [])
    if not channels:
        print(f"[WARN] file_shared 이벤트에 채널 정보 없음: {file_id}")
        return

    channel = channels[0]
    thread_ts = file_info.get("shares", {}).get("public", {}).get(channel, [{}])[0].get("ts")

    def reply(text):
        client.chat_postMessage(channel=channel, text=text, thread_ts=thread_ts)

    reply("🎙️ 녹음 파일 감지! 회의록 생성을 시작합니다...")

    response = requests.get(
        file_info["url_private_download"],
        headers={"Authorization": f"Bearer {os.getenv('SLACK_BOT_TOKEN')}"},
    )

    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        tmp.write(response.content)
        tmp_path = tmp.name

    try:
        reply("📝 음성 → 텍스트 변환 중...")
        stt = get_stt(config)
        transcript = stt.transcribe(tmp_path)
        print(f"[STT 결과]\n{transcript[:200]}...")

        reply("🤖 회의록 작성 및 게시 중...")
        page_url = generate_and_publish(transcript)

        reply(f"✅ 회의록이 생성되었습니다!\n{page_url}")

    except Exception as e:
        reply(f"❌ 오류가 발생했습니다: {str(e)}")
        raise

    finally:
        os.unlink(tmp_path)


# ── Claude로 회의록 생성 ──────────────────────────────────
def generate_minutes(transcript: str, template: str = "") -> tuple[str, str]:
    """회의록 제목과 HTML 본문을 생성하여 (title, body_html) 튜플로 반환한다."""
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

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

    response = client.messages.create(
        model="claude-sonnet-4-5-20250514",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )

    text = ""
    for block in response.content:
        if hasattr(block, "text"):
            text += block.text

    lines = text.strip().split("\n", 1)
    title = lines[0].strip().removeprefix("#").strip()
    body_html = lines[1].strip() if len(lines) > 1 else ""

    return title, body_html


# ── 회의록 생성 + 게시 ────────────────────────────────────
def generate_and_publish(transcript: str) -> str:
    publisher = get_publisher(config)
    template = publisher.get_template()
    title, body_html = generate_minutes(transcript, template)
    return publisher.publish(title, body_html)


# ── 실행 ───────────────────────────────────────────────────
if __name__ == "__main__":
    start_health_server()

    app_token = os.getenv("SLACK_APP_TOKEN")
    if not app_token:
        print("❌ SLACK_APP_TOKEN 환경변수가 설정되지 않았습니다.")
        exit(1)
    if not app_token.startswith("xapp-"):
        print(f"⚠️ SLACK_APP_TOKEN이 'xapp-'으로 시작하지 않습니다: {app_token[:10]}...")

    print("🚀 회의록 에이전트 시작")
    print("🔌 Socket Mode 연결 시도 중...")

    try:
        handler = SocketModeHandler(app, app_token)
        handler.start()
    except Exception as e:
        print(f"❌ Socket Mode 연결 실패: {e}")
        exit(1)
