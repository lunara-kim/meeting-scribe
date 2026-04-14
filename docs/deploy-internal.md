# 내부환경 배포/사용 매뉴얼

사내망/온프레미스 기반 구성. 외부 API 사용이 제한되거나 보안 요구로 데이터가 외부로 나가면 안 되는 환경용.

## 구성

| 계층 | 사용 서비스 |
|------|-------------|
| Trigger | Slack (Socket Mode) **또는** NAVER WORKS Bot (Callback URL) |
| STT  | Whisper (local) |
| LLM  | Ollama (로컬 LLM) |
| Publisher | Confluence (사내 Atlassian Cloud/Server) |
| Hosting | 사내 Linux 서버 (Docker) |

트리거는 `config.yaml`의 `trigger.provider`로 스위칭한다 (`slack` | `naverworks`).

---

## 1. 사전 준비물 — 공통

### 1-1. Ollama 서버
LLM 추론용 로컬 LLM 서버.

**설치** (Linux):
```bash
curl -fsSL https://ollama.com/install.sh | sh
```

**모델 다운로드**:
```bash
# 한국어 회의록 품질을 위해 Llama 3.1 8B 이상 권장
ollama pull llama3.1:8b
# 또는 더 큰 모델
ollama pull llama3.1:70b
```

**API 서버 기동 확인**:
```bash
curl http://localhost:11434/api/tags
```

meeting-scribe와 같은 호스트에 띄우면 `http://localhost:11434`, 별도 서버면 `http://<ollama-host>:11434` 사용.

### 1-2. Confluence 권한
- 회의록을 게시할 **부모 페이지** 결정 → URL에서 page ID 추출
  - 예) `https://hectoinno.atlassian.net/wiki/spaces/TF/pages/323190803/...` → `323190803`
- 해당 Space key 확인 (URL의 `spaces/TF` 부분)
- **Atlassian API Token** 발급: https://id.atlassian.com/manage-profile/security/api-tokens → Create → `ATATT3...` 복사

### 1-3. 내부 서버 요구사항
- Linux (Ubuntu 22.04 권장)
- Docker 24+
- 네트워크: 사용하는 트리거에 따라 다름 (아래 1-A / 1-B 참조), 사내 Confluence, Ollama 서버 접근 가능

---

## 1-A. 트리거 — Slack (Socket Mode)

외부환경과 동일. `docs/deploy-external.md`의 **1-1** 참조.

> Socket Mode는 아웃바운드 WebSocket 연결이므로 사내망에서도 Slack API 접근만 허용되면 동작한다. 방화벽에서 `*.slack.com` 443/TCP **아웃바운드** 허용 필요.

---

## 1-B. 트리거 — NAVER WORKS Bot (Callback URL)

사내 NAVER WORKS를 메신저로 사용하는 환경용. Slack과 달리 **Callback URL(인바운드 HTTPS)** 방식이므로 네트워크 준비가 필요하다.

### 1-B-1. 네트워크 준비 (필수)

NAVER WORKS는 `*.worksmobile.com` 서버가 우리 봇 서버로 HTTPS POST를 보낸다.

- 봇 서버가 **인터넷에서 HTTPS로 접근 가능**해야 함
- 공인 도메인(예: `bot.hecto.co.kr`) + SSL 인증서 필요
- 사내망인 경우 일반적인 선택지:
  - (a) **DMZ/리버스 프록시**: 공인 IP를 가진 nginx가 `/callback`을 내부 봇 서버로 포워딩
  - (b) **아웃바운드 터널**: Cloudflare Tunnel 등 (보안팀 허용 필요)

### 1-B-2. Developer Console — App 등록

https://developers.worksmobile.com/ 접속 → **Console → App → 새 App 생성**

발급받을 값:
- **Client ID** / **Client Secret**
- **Service Account** (예: `xxxxx.serviceaccount@<domain>`)
- **Private Key** (RS256 PEM — 다운로드 1회만 가능, 분실 시 재발급)
- Scopes: `bot`

### 1-B-3. Developer Console — Bot 생성/등록

**Bot → 새 Bot 생성**:
- **Bot ID** / **Bot Secret** (Callback 서명 검증용)
- Callback 이벤트: `message` 활성화 (파일 첨부 이벤트 포함)
- Callback URL: `https://bot.hecto.co.kr/callback` (1-B-1에서 준비한 주소)

생성한 Bot을 **도메인에 등록**해야 사용자가 볼 수 있다. Admin → 서비스 → Bot → 등록.

### 1-B-4. 네트워크 방화벽

- **인바운드**: 인터넷 → 봇 서버 443/TCP (Callback 수신)
- **아웃바운드**: `auth.worksmobile.com`, `www.worksapis.com` 443/TCP 허용
  - Access Token 발급 + 첨부파일 다운로드 + 메시지 전송

---

## 2. 설정 파일

`config.yaml` 예시 (NAVER WORKS + Ollama + Confluence):

```yaml
stt:
  provider: whisper_local
  whisper_local:
    model_size: medium           # tiny/base/small/medium/large (클수록 정확, 느림)

llm:
  provider: ollama
  ollama:
    base_url: http://ollama-server:11434   # 또는 http://localhost:11434
    model: llama3.1:8b
    timeout: 600                            # 로컬 추론은 느리니 넉넉히

publisher:
  provider: confluence
  confluence:
    base_url: https://hectoinno.atlassian.net/wiki
    space_key: TF
    parent_page_id: "323190803"
    user_email: your.email@hecto.co.kr
    api_token: ${ATLASSIAN_API_TOKEN}

trigger:
  provider: naverworks           # slack / naverworks
  slack:
    bot_token: ${SLACK_BOT_TOKEN}
    app_token: ${SLACK_APP_TOKEN}
  naverworks:
    client_id: ${NAVERWORKS_CLIENT_ID}
    client_secret: ${NAVERWORKS_CLIENT_SECRET}
    service_account: ${NAVERWORKS_SERVICE_ACCOUNT}
    bot_id: ${NAVERWORKS_BOT_ID}
    bot_secret: ${NAVERWORKS_BOT_SECRET}
    private_key: ${NAVERWORKS_PRIVATE_KEY}           # PEM 문자열 직접 주입
    # private_key_path: /app/secrets/naverworks-private.key   # 또는 파일 마운트
    callback_host: 0.0.0.0
    callback_port: 3000
    callback_path: /callback
```

> Slack을 쓰려면 `trigger.provider: slack`로 바꾸면 된다. 한 쪽 설정이 비어 있어도 문제 없다 — 선택된 provider만 읽힌다.

---

## 3. 배포 (Docker)

### 3-1. 이미지 빌드
```bash
git clone https://github.com/lunara-kim/meeting-scribe.git
cd meeting-scribe
docker build -t meeting-scribe:latest .
```

### 3-2. `.env` 파일 작성

**Slack 트리거 사용 시**:
```bash
cat > .env <<EOF
SLACK_BOT_TOKEN=xoxb-...
SLACK_APP_TOKEN=xapp-...
ATLASSIAN_API_TOKEN=ATATT3...
EOF
chmod 600 .env
```

**NAVER WORKS 트리거 사용 시**:
```bash
cat > .env <<'EOF'
NAVERWORKS_CLIENT_ID=xxxx
NAVERWORKS_CLIENT_SECRET=xxxx
NAVERWORKS_SERVICE_ACCOUNT=xxxx.serviceaccount@domain
NAVERWORKS_BOT_ID=12345678
NAVERWORKS_BOT_SECRET=xxxx
NAVERWORKS_PRIVATE_KEY="-----BEGIN PRIVATE KEY-----\nMIIE...\n-----END PRIVATE KEY-----\n"
ATLASSIAN_API_TOKEN=ATATT3...
EOF
chmod 600 .env
```

> `NAVERWORKS_PRIVATE_KEY`는 PEM 전체를 한 줄에 넣되 개행은 `\n`으로 이스케이프하거나, 또는 파일로 두고 `private_key_path`를 사용해 마운트한다.

### 3-3. 실행

**Slack**:
```bash
docker run -d \
  --name meeting-scribe \
  --restart unless-stopped \
  --env-file .env \
  -v $(pwd)/config.yaml:/app/config.yaml:ro \
  -p 8080:8080 \
  meeting-scribe:latest
```

**NAVER WORKS** (Callback 수신용 3000 포트 추가 노출):
```bash
docker run -d \
  --name meeting-scribe \
  --restart unless-stopped \
  --env-file .env \
  -v $(pwd)/config.yaml:/app/config.yaml:ro \
  -p 8080:8080 \
  -p 3000:3000 \
  meeting-scribe:latest
```

> 3000 포트는 리버스 프록시(nginx 등)를 통해 HTTPS로 외부에 노출해야 한다. 예시:
> ```nginx
> location /callback {
>   proxy_pass http://127.0.0.1:3000/callback;
>   proxy_set_header X-WORKS-Signature $http_x_works_signature;
> }
> ```

### 3-4. 로그 확인
```bash
docker logs -f meeting-scribe
```

정상 기동 로그 (Slack):
```
🩺 Health check server started on :8080
🚀 회의록 에이전트 시작 (trigger: slack)
🔌 Slack Socket Mode 연결 시도 중...
⚡️ Bolt app is running!
```

정상 기동 로그 (NAVER WORKS):
```
🩺 Health check server started on :8080
🚀 회의록 에이전트 시작 (trigger: naverworks)
🔑 NAVER WORKS access token 발급 완료
🌐 NAVER WORKS Callback 수신 대기: 0.0.0.0:3000/callback
```

---

## 4. 운영 명령어

```bash
# 재시작
docker restart meeting-scribe

# 중지/삭제
docker stop meeting-scribe && docker rm meeting-scribe

# 설정 변경 후 재적용 (config.yaml만 바꾼 경우 컨테이너 재시작만)
docker restart meeting-scribe

# 이미지 업데이트
git pull
docker build -t meeting-scribe:latest .
docker stop meeting-scribe && docker rm meeting-scribe
# 다시 3-3 실행
```

### 시스템 서비스로 등록 (선택)
`/etc/systemd/system/meeting-scribe.service`:
```ini
[Unit]
Description=Meeting Scribe Bot
After=docker.service
Requires=docker.service

[Service]
Restart=always
ExecStart=/usr/bin/docker start -a meeting-scribe
ExecStop=/usr/bin/docker stop -t 10 meeting-scribe

[Install]
WantedBy=multi-user.target
```
```bash
sudo systemctl enable --now meeting-scribe
```

---

## 5. 사용법

### Slack
외부환경과 동일. `docs/deploy-external.md`의 **5. 사용법** 참조.

### NAVER WORKS
1. 봇을 대화방/채널에 초대
2. 오디오 파일(`.m4a`, `.mp3`, `.wav`, `.mp4`, `.ogg`, `.webm`, `.flac`)을 채널에 업로드
3. 봇이 자동으로 감지 → STT → 회의록 → Confluence 게시
4. 완료 시 결과 URL을 같은 채널에 회신

결과 페이지 URL은 Confluence로 표시된다:
```
✅ 회의록이 생성되었습니다!
https://hectoinno.atlassian.net/wiki/pages/<page-id>
```

---

## 6. 트러블슈팅

| 증상 | 원인 | 해결 |
|------|------|------|
| Ollama 연결 실패 | Ollama 서버 미기동 또는 방화벽 | `curl http://<host>:11434/api/tags` 로 접근성 확인 |
| LLM 응답이 잘림 | 모델 컨텍스트 한계 | 더 큰 모델(`llama3.1:70b`) 또는 `max_tokens` 조정 |
| Whisper 메모리 부족 | `model_size: large` 로드 실패 | `medium` 또는 `small`로 낮추기 |
| Confluence 401 | API Token 만료 또는 잘못된 email | API Token 재발급, `user_email`은 Atlassian 계정 email |
| Confluence 400 | Space key 또는 parent_page_id 오류 | 실제 URL에서 값 재확인 |
| 첫 추론이 매우 느림 | Ollama가 모델을 메모리로 로드 중 | 재기동 직후 warm-up 요청 1회 권장 |
| Slack Socket Mode 연결 안 됨 | 방화벽이 `*.slack.com` WebSocket 차단 | 사내 네트워크팀에 Slack WebSocket(443/TCP outbound) 허용 요청 |
| NAVER WORKS Callback 401 | `bot_secret` 불일치 → HMAC 서명 검증 실패 | Developer Console Bot 화면의 Bot Secret과 일치하는지 확인 |
| NAVER WORKS 토큰 발급 실패 | Service Account, Client ID/Secret, 개인키 불일치 | Developer Console에서 값 재확인, 개인키 PEM 개행 처리 확인 |
| NAVER WORKS 파일 다운로드 실패 | 첨부파일 만료(일정 시간 후 삭제) 또는 토큰 스코프 부족 | Bot에 `bot` scope 부여, 업로드 직후 짧은 시간 내 처리되도록 유지 |
| Callback이 아예 오지 않음 | 인바운드 방화벽/리버스 프록시 설정, TLS 인증서 | `curl -X POST https://<도메인>/callback` 외부망에서 200/401 응답 오는지 확인 |

---

## 7. 성능 튜닝 팁

### Whisper (STT)
- `tiny` / `base`: 빠르지만 한국어 품질 떨어짐
- `small`: 가벼운 회의용 권장
- `medium`: **일반 회의 기본값** (권장)
- `large-v3`: 최고 품질, GPU 권장

### Ollama (LLM)
- `llama3.1:8b`: CPU로도 수분 내 동작
- `llama3.1:70b`: GPU(VRAM 40GB+) 권장, 품질 높음
- 한국어 특화: `EEVE-Korean-10.8B` 등 한국어 파인튜닝 모델도 고려

### 하드웨어
- Whisper medium + Ollama 8b: CPU 8코어 / RAM 16GB 최소
- Whisper large + Ollama 70b: GPU 필수 (RTX 4090 또는 A100 수준)
