# meeting-scribe

Slack / NAVER WORKS에서 음성 파일을 받아 Whisper로 전사하고 Claude로 회의록을 작성해 Notion/Confluence에 게시하는 봇.

> 상위 `C:\Users\hi\git\CLAUDE.md`의 Jenkins/GitLab/Jira 기반 워크플로우는 이 프로젝트엔 적용되지 않는다. 이 프로젝트는 GitHub + GitHub Actions + Fly.io 기반이며, 아래 규칙이 우선한다.

## 아키텍처

4계층 플러그인 구조. 각 계층은 인터페이스에 맞는 구현체 여러 개를 두고 `config.yaml`의 `provider` 값으로 선택한다.

```
Trigger → STT → LLM → Publisher
```

- `trigger/` — `base.py`의 `Trigger`, `AudioEvent` 계약. 현재 `slack` (Socket Mode), `naverworks` (Flask 콜백 + JWT)
- `stt/` — `whisper_api` (활성), `whisper_local` (미사용)
- `llm/` — `anthropic` (활성, Claude Sonnet 4.5), `ollama` (미사용)
- `publisher/` — `notion` (활성), `confluence` (템플릿 미구현)
- `main.py` — 오케스트레이터. `on_audio(event)` 콜백이 STT → LLM → Publish 수행
- 헬스체크 — `main.py`의 `HealthHandler`가 `:8080 GET /` 응답 (Fly.io liveness)

새 provider 추가 시 계약은 각 패키지의 `__init__.py` / `base.py` 참고.

## 개발 규칙

- Python 3.11+, 타입힌트 사용
- **시크릿은 환경변수로만** 주입. `config.yaml`은 `${VAR}` 참조만 쓰고 값은 `.env` 또는 GitHub Actions / Fly secrets로 넣는다
- **Provider 추가/변경은 config 스위치로**. 하드코딩된 분기 금지
- **외부 API 호출은 재시도**. Slack 다운로드 재시도(`trigger/slack.py`, commit 5c9a536) 패턴을 참고
- **로깅**: 현재 `print()` 다수 → `logging` 모듈로 점진 마이그레이션 중. 신규 코드는 `logging` 사용
- **Notion 텍스트 분할은 UTF-16 code unit 기준** (commit 20ba05c). Python 문자 수로 자르면 한글에서 2000자 제한 초과해 실패한다

## 알려진 제약

- Whisper API는 25MB / ~25분 제한. 긴 오디오 청킹은 아직 없음
- `publisher/confluence.py`의 `get_template()`는 빈 문자열 반환 — 템플릿 기능 미구현
- `stt/whisper_local.py`, `llm/ollama_llm.py`는 참조용. 프로덕션에선 미검증
- 파이프라인은 블로킹. 동시 요청 큐잉 없음

## 자주 쓰는 명령어

```bash
pip install -r requirements.txt
pip install -r requirements-dev.txt # pytest 포함 개발 의존성
python main.py                      # 로컬 실행 (.env 필요)
python -m pytest                    # 테스트 (외부 API는 전부 mock)
fly logs -a meeting-scribe          # 운영 로그
fly secrets set KEY=value -a meeting-scribe
```

배포는 `main` push → `.github/workflows/deploy.yml` → Fly.io 자동. 수동 배포는 `fly deploy`.

## 커밋 컨벤션

```
{type}: {한글 또는 영문 설명}
```

- type: `feat` / `fix` / `refactor` / `chore` / `docs` / `test`
- scope·이슈번호 없음 (최근 로그 기준)
- 예: `feat: abstract trigger layer and add NAVER WORKS bot support`

## 작업 워크플로우

개인 GitHub repo 기준 간소화 버전:

1. 이슈 기반 작업이면 GitHub Issue 먼저 생성 (필수 아님)
2. 브랜치: `{type}/{짧은-슬러그}` 또는 `{issue#}-{슬러그}`
3. 구현 → 로컬 `python main.py`로 수동 검증 (자동화 테스트 없음)
4. 커밋 → push → PR
5. 자기 리뷰 후 squash merge
6. `main` 머지 시 GitHub Actions가 Fly.io에 자동 배포
7. `fly logs`로 배포 확인

테스트는 `python -m pytest`. 외부 API(Slack/Whisper/Anthropic/Notion/Confluence)는 전부 mock되므로 시크릿 없이 실행 가능. 새 provider 추가 시 `tests/`에 단위테스트 + 골든 경로 추가.

## 파일 구조

```
meeting-scribe/
├── main.py                  # 오케스트레이터 + 헬스 서버
├── config.yaml              # provider 선택 + ${ENV} 참조
├── .env.example
├── trigger/{slack,naverworks,base}.py
├── stt/{whisper_api,whisper_local}.py
├── llm/{anthropic_llm,ollama_llm}.py
├── publisher/{notion,confluence}.py
├── docs/deploy-{internal,external}.md
├── Dockerfile
├── fly.toml                 # nrt 리전, 512MB, auto_stop off
└── .github/workflows/deploy.yml
```
