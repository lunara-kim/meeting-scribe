# 외부환경 배포/사용 매뉴얼

SaaS/퍼블릭 클라우드 기반 구성. 회사 방화벽/VPN 제약이 없는 개인·소규모 팀용.

## 구성

| 계층 | 사용 서비스 |
|------|-------------|
| STT  | OpenAI Whisper API |
| LLM  | Anthropic Claude |
| Publisher | Notion |
| Hosting | Fly.io (Tokyo 리전) |

---

## 1. 사전 준비물

### 1-1. Slack App 생성
1. https://api.slack.com/apps → **Create New App** → *From scratch*
2. App Name, 워크스페이스 선택
3. 아래 메뉴에서 각각 설정:
   - **Socket Mode** → Enable → App-Level Token 생성 (scope: `connections:write`) → `xapp-...` 복사 (= `SLACK_APP_TOKEN`)
   - **OAuth & Permissions** → Bot Token Scopes 추가:
     - `app_mentions:read`
     - `channels:history`
     - `chat:write`
     - `files:read`
   - **Event Subscriptions** → Enable → Subscribe to bot events:
     - `app_mention`
     - `file_shared`
   - **Install App** → 워크스페이스 설치 → Bot Token (`xoxb-...`) 복사 (= `SLACK_BOT_TOKEN`)

> ⚠️ Event Subscriptions는 Socket Mode를 먼저 켠 뒤에 저장해야 Request URL 검증 없이 저장된다.

### 1-2. OpenAI API Key
- https://platform.openai.com/api-keys → Create → `sk-...` 복사 (= `OPENAI_API_KEY`)
- 결제 수단 등록 및 Usage 한도 확인

### 1-3. Anthropic API Key
- https://console.anthropic.com/settings/keys → Create Key → `sk-ant-...` 복사 (= `ANTHROPIC_API_KEY`)
- Plans & Billing에서 크레딧 충전

### 1-4. Notion Integration
1. https://www.notion.so/profile/integrations → **New integration**
2. 타입 *Internal*, 워크스페이스 선택, Submit
3. Configuration 탭에서 **Internal Integration Secret** (`ntn_...`) 복사 (= `NOTION_API_TOKEN`)
4. Notion에서 회의록을 저장할 **부모 페이지**와 **양식 페이지** 각각:
   - 우측 상단 `•••` → **Connections** → 만든 Integration 추가
5. 각 페이지 URL 끝의 32자 해시가 page_id
   - 예) `https://notion.so/My-Meetings-3413037f90f18059b795cefabf60ea19` → `3413037f90f18059b795cefabf60ea19`

### 1-5. Fly.io 계정
- https://fly.io/app/sign-up → 가입
- 로컬에 `flyctl` 설치 ([가이드](https://fly.io/docs/flyctl/install/))
- `fly auth login`

---

## 2. 설정 파일

`config.yaml`:
```yaml
stt:
  provider: whisper_api
  whisper_api:
    api_key: ${OPENAI_API_KEY}

llm:
  provider: anthropic
  anthropic:
    api_key: ${ANTHROPIC_API_KEY}
    model: claude-sonnet-4-5
    max_tokens: 4096

publisher:
  provider: notion
  notion:
    parent_page_id: "여기에 부모 페이지 ID"
    template_page_id: "여기에 양식 페이지 ID"  # 선택
    api_token: ${NOTION_API_TOKEN}

slack:
  bot_token: ${SLACK_BOT_TOKEN}
  app_token: ${SLACK_APP_TOKEN}
```

---

## 3. 배포

### 3-1. Fly 앱 생성 (최초 1회)
```bash
fly launch --no-deploy --name lunara-meeting-scribe --region nrt
```

### 3-2. 시크릿 등록
```bash
fly secrets set \
  SLACK_BOT_TOKEN=xoxb-... \
  SLACK_APP_TOKEN=xapp-... \
  OPENAI_API_KEY=sk-... \
  ANTHROPIC_API_KEY=sk-ant-... \
  NOTION_API_TOKEN=ntn_... \
  -a lunara-meeting-scribe
```

### 3-3. 배포
```bash
fly deploy -a lunara-meeting-scribe
```

또는 GitHub Actions 연동: `main` 브랜치 푸시 시 자동 배포되도록 `.github/workflows/deploy.yml` 구성됨.

---

## 4. 운영 명령어

```bash
# 상태 확인
fly status -a lunara-meeting-scribe

# 실시간 로그
fly logs -a lunara-meeting-scribe

# 시크릿 목록
fly secrets list -a lunara-meeting-scribe

# 머신 재시작
fly machine restart <machine-id> -a lunara-meeting-scribe
```

정상 기동 로그:
```
🩺 Health check server started on :8080
🚀 회의록 에이전트 시작
🔌 Socket Mode 연결 시도 중...
⚡️ Bolt app is running!
```

---

## 5. 사용법

### 방법 A: 파일 업로드 → 자동 감지
채널에 오디오 파일(`.mp3`, `.m4a`, `.wav`, `.ogg`, `.webm`, `.flac`, `.mp4`)을 업로드하면 봇이 자동으로 감지하고 처리한다.

### 방법 B: 스레드에서 멘션
오디오 파일이 있는 메시지의 스레드에서 `@meeting-scribe` 멘션 → 해당 스레드의 첫 오디오 파일을 처리.

### 진행 메시지
```
🎙️ 녹음 파일 감지! 회의록 생성을 시작합니다...
📝 음성 → 텍스트 변환 중...
🤖 회의록 작성 및 게시 중...
✅ 회의록이 생성되었습니다!
https://www.notion.so/...
```

---

## 6. 트러블슈팅

| 증상 | 원인 | 해결 |
|------|------|------|
| 멘션해도 로그 없음 | Event Subscriptions 미설정 또는 봇이 채널 미참여 | 구독 이벤트 확인, `/invite @meeting-scribe` |
| `Invalid file format` | `file_shared` 이벤트가 업로드 완료 전 도착 | 현재 코드는 최대 5회 재시도로 자동 복구 |
| `credit balance is too low` | Anthropic 크레딧 부족 | https://console.anthropic.com/settings/billing 에서 충전 |
| Notion 400 `object_not_found` | Integration이 부모 페이지에 연결 안 됨 | 해당 페이지 Connections에 Integration 추가 |
| Socket Mode 연결 실패 | `SLACK_APP_TOKEN` 미설정 또는 잘못된 값 | `xapp-`으로 시작하는 App-Level Token인지 확인 |
