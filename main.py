import os
import base64
import tempfile

import yaml
import requests
import anthropic
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from dotenv import load_dotenv

from stt import get_stt

load_dotenv()

# ── 설정 로드 ──────────────────────────────────────────────
with open("config.yaml") as f:
    config = yaml.safe_load(f)

# ── Slack 앱 초기화 ────────────────────────────────────────
app = App(token=os.getenv("SLACK_BOT_TOKEN"))

AUDIO_EXTENSIONS = {".mp3", ".mp4", ".wav", ".m4a", ".ogg", ".webm", ".flac"}


# ── Slack 이벤트 핸들러 ────────────────────────────────────
@app.event("file_shared")
def on_file_shared(event, client, say):
    file_info = client.files_info(file=event["file_id"])["file"]
    filename = file_info.get("name", "")
    ext = os.path.splitext(filename)[1].lower()

    if ext not in AUDIO_EXTENSIONS:
        return  # 오디오 파일이 아니면 무시

    say("🎙️ 녹음 파일 감지! 회의록 생성을 시작합니다...")

    # 파일 다운로드
    response = requests.get(
        file_info["url_private_download"],
        headers={"Authorization": f"Bearer {os.getenv('SLACK_BOT_TOKEN')}"},
    )

    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        tmp.write(response.content)
        tmp_path = tmp.name

    try:
        # STT 변환
        say("📝 음성 → 텍스트 변환 중...")
        stt = get_stt(config)
        transcript = stt.transcribe(tmp_path)
        print(f"[STT 결과]\n{transcript[:200]}...")

        # 회의록 생성 + Confluence 게시
        say("🤖 회의록 작성 및 Confluence 게시 중...")
        page_url = generate_and_publish(transcript)

        say(f"✅ 회의록이 생성되었습니다!\n{page_url}")

    except Exception as e:
        say(f"❌ 오류가 발생했습니다: {str(e)}")
        raise

    finally:
        os.unlink(tmp_path)


# ── Claude + Atlassian MCP로 회의록 생성 + 게시 ────────────
def generate_and_publish(transcript: str) -> str:
    cfg_a = config["atlassian"]
    cfg_c = config["confluence"]

    # Atlassian Basic Auth 토큰 생성
    email = cfg_a["user_email"]
    token = os.getenv("ATLASSIAN_API_TOKEN")
    auth_token = base64.b64encode(f"{email}:{token}".encode()).decode()

    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    prompt = f"""다음 순서대로 진행해주세요.

1. Confluence 페이지(ID: {cfg_c['template_page_id']})를 읽어서 회의록 양식을 파악하세요.
2. 아래 [STT 결과]를 바탕으로 해당 양식에 맞게 한국어로 회의록을 작성하세요.
3. 작성한 회의록을 Confluence에 새 페이지로 게시하세요.
   - space_key: {cfg_c['space_key']}
   - parent_page_id: {cfg_c['parent_page_id']}
   - 제목: 회의록 - [회의 날짜 및 주제]
4. 생성된 페이지의 URL만 반환하세요.

[STT 결과]
{transcript}
"""

    response = client.beta.messages.create(
        model="claude-opus-4-5",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
        mcp_servers=[
            {
                "type": "url",
                "url": "https://mcp.atlassian.com/v1/mcp",
                "name": "atlassian",
                "authorization_token": auth_token,
            }
        ],
        betas=["mcp-client-2025-04-04"],
    )

    for block in response.content:
        if hasattr(block, "text") and block.text.strip():
            return block.text.strip()

    return "(페이지 URL을 가져오지 못했습니다)"


# ── 실행 ───────────────────────────────────────────────────
if __name__ == "__main__":
    print("🚀 회의록 에이전트 시작")
    SocketModeHandler(app, os.getenv("SLACK_APP_TOKEN")).start()
