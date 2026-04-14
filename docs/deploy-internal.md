# 내부환경 배포/사용 매뉴얼

사내망/온프레미스 기반 구성. 외부 API 사용이 제한되거나 보안 요구로 데이터가 외부로 나가면 안 되는 환경용.

## 구성

| 계층 | 사용 서비스 |
|------|-------------|
| STT  | Whisper (local) |
| LLM  | Ollama (로컬 LLM) |
| Publisher | Confluence (사내 Atlassian Cloud/Server) |
| Hosting | 사내 Linux 서버 (Docker) |

---

## 1. 사전 준비물

### 1-1. Slack App
외부환경과 동일. `docs/deploy-external.md`의 **1-1** 참조.

> Socket Mode는 아웃바운드 WebSocket 연결이므로 사내망에서도 Slack API 접근만 허용되면 동작한다. 방화벽에서 `*.slack.com` 허용 필요.

### 1-2. Ollama 서버
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

### 1-3. Confluence 권한
- 회의록을 게시할 **부모 페이지** 결정 → URL에서 page ID 추출
  - 예) `https://hectoinno.atlassian.net/wiki/spaces/TF/pages/323190803/...` → `323190803`
- 해당 Space key 확인 (URL의 `spaces/TF` 부분)
- **Atlassian API Token** 발급: https://id.atlassian.com/manage-profile/security/api-tokens → Create → `ATATT3...` 복사

### 1-4. 내부 서버 요구사항
- Linux (Ubuntu 22.04 권장)
- Docker 24+
- 네트워크: Slack API(`*.slack.com`), 사내 Confluence, Ollama 서버 접근 가능

---

## 2. 설정 파일

`config.yaml`:
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

slack:
  bot_token: ${SLACK_BOT_TOKEN}
  app_token: ${SLACK_APP_TOKEN}
```

---

## 3. 배포 (Docker)

### 3-1. 이미지 빌드
```bash
git clone https://github.com/lunara-kim/meeting-scribe.git
cd meeting-scribe
docker build -t meeting-scribe:latest .
```

### 3-2. `.env` 파일 작성
```bash
cat > .env <<EOF
SLACK_BOT_TOKEN=xoxb-...
SLACK_APP_TOKEN=xapp-...
ATLASSIAN_API_TOKEN=ATATT3...
EOF
chmod 600 .env
```

### 3-3. 실행
```bash
docker run -d \
  --name meeting-scribe \
  --restart unless-stopped \
  --env-file .env \
  -v $(pwd)/config.yaml:/app/config.yaml:ro \
  -p 8080:8080 \
  meeting-scribe:latest
```

### 3-4. 로그 확인
```bash
docker logs -f meeting-scribe
```

정상 기동 로그:
```
🩺 Health check server started on :8080
🚀 회의록 에이전트 시작
🔌 Socket Mode 연결 시도 중...
⚡️ Bolt app is running!
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
Description=Meeting Scribe Slack Bot
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

외부환경과 동일. `docs/deploy-external.md`의 **5. 사용법** 참조.

결과 페이지 URL만 Confluence로 바뀐다:
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
