# Feature: 구조적 로깅 도입
_생성일: 2026-04-14 | 마지막 업데이트: 2026-04-14_

> ✅ 완료됨 — 2026-04-14
> 핵심 결정은 docs/adr/0001-*.md, docs/adr/0002-*.md 로 승격되었습니다.

> 이 파일은 Context Anchoring 문서입니다.
> 새 세션 시작 시 이 파일을 Claude에게 공유하세요.
> `/anchor` 커맨드로 세션이 끝날 때마다 업데이트하세요.
> 피처 완료 시 `/anchor-graduate`로 핵심 결정을 ADR로 승격하세요.

## Decisions
| 결정 | 이유 | 거절한 대안 |
|------|------|------------|
| 표준 라이브러리 `logging` + 자체 JSON formatter 채택 | 외부 의존성 없이 Fly.io 로그 수집기가 파싱 가능한 한 줄 JSON 생성. 의존성 최소화가 프로젝트 기조(requirements.txt 얇게 유지) | `python-json-logger`, `structlog`, `loguru` — 편리하지만 단순 포맷 하나 만들자고 신규 의존성 추가는 과함 |
| `LOG_LEVEL` / `LOG_FORMAT` 환경변수로 런타임 제어 (기본: INFO / json) | Fly secrets로 변경 가능해야 운영 중 디버그 레벨 전환이 쉽고, 로컬 개발에선 `LOG_FORMAT=plain`으로 읽기 편함 | config.yaml에 박제 — provider 스위치와 달리 운영 중 바꿔야 해서 env가 맞음 |
| `logger.exception()`으로 에러 경로 통일, 스택트레이스 자동 포함 | 기존 `print(f"❌ {e}")`는 스택 유실. 운영 디버깅에 필수 | `logger.error(..., exc_info=True)` — 가능하지만 의도가 덜 명시적 |
| `extra={...}`로 구조화 컨텍스트 주입 (file_id, attempt, bytes 등) | JSON 필드로 바로 쿼리 가능. f-string으로 메시지에 비비면 파싱 필요 | 메시지 문자열에 포매팅 — 사람이 읽기는 쉽지만 기계 파싱 불가 |
| LogRecord 예약어 회피 규칙 (`filename` → `audio_filename`) | `extra`에 `filename` 넣으면 `KeyError: Attempt to overwrite 'filename'` 발생. 테스트에서 실제로 터짐 | 예약어 검사 자동화 — 오버엔지니어링. 네이밍 규칙으로 충분 |
| 시끄러운 외부 라이브러리(`urllib3`, `slack_bolt`, `slack_sdk`, `werkzeug`) WARNING으로 억제 | Socket Mode / Flask 기본 DEBUG가 시그널을 묻음 | 전체 DEBUG — Fly 로그 비용/노이즈 증가 |
| `setup_logging()`을 `main.py` 최상단에서 1회 호출, idempotent 가드 | 모듈 import 순서에 덜 취약하고, 테스트에서 여러 번 호출돼도 핸들러 중복 안 됨 | import-time 자동 설정 — 테스트 격리 깨짐 |

## Constraints
- Python 3.11+ 표준 라이브러리만 사용 (logging/json/datetime)
- Fly.io 로그는 stdout을 줄 단위로 수집 — formatter가 한 줄 JSON을 보장해야 함
- 기존 print() 스타일(이모지, 한글 메시지)은 JSON `msg` 필드로 이전되며 의미는 유지하되 키 이름은 영문 snake_case
- LogRecord 예약 속성(`filename`, `module`, `name`, `levelname` 등)은 `extra`에 사용 금지

## Open Questions
- [ ] `main.py`의 `setup_logging()` 최상단 호출이 테스트에서 항상 동작하는지(현재는 통과) 장기적으로 핸들러 주입 패턴이 더 낫지 않을지
- [ ] `LOG_LEVEL=DEBUG`일 때 민감정보(Slack 토큰 prefix, Notion response body) 마스킹 정책 필요 여부
- [x] print()를 전부 교체할지 점진 이전할지 (해결: 일괄 교체. 22곳뿐이라 부분 이전이 오히려 스타일 혼재)
- [x] JSON formatter를 외부 패키지로 갈지 자체 구현할지 (해결: 자체 구현, 30줄로 충분)

## State
- [x] `logging_config.py` 신규 (`setup_logging`, `JsonFormatter`)
- [x] `main.py`, `trigger/slack.py`, `trigger/naverworks.py`, `stt/whisper_api.py`, `stt/whisper_local.py`, `publisher/notion.py`의 `print()` 전량 교체
- [x] 에러 경로 `logger.exception()`로 통일
- [x] pytest 34개 통과, JSON 출력 스모크 테스트 확인
- [x] 커밋 + `main` push (`e66a8ee feat: introduce structured JSON logging`)
- [ ] Critical #2: Whisper/Claude/Notion 외부 호출 재시도 (지수 백오프) — 다음 작업
- [ ] Fly.io 배포 후 실제 수집 로그에서 JSON 파싱/필드 확인
- [ ] README에 `LOG_LEVEL` / `LOG_FORMAT` 문서화

## Session Log
### 2026-04-14
- 미커밋 변경(main.py utf-8 encoding fix, pytest setup + tests/, CLAUDE.md) 3개 커밋으로 나눠 push
- 남은 고도화 항목 현황 점검 (#1 로깅, #2 재시도, #4 Confluence 템플릿 등 미착수 확인)
- **구조적 로깅 도입**: stdlib logging + 자체 JsonFormatter로 22곳의 print() 일괄 교체
  - `extra={}`에 `filename` 키 사용 시 LogRecord 충돌로 테스트 1개 실패 → `audio_filename`으로 리네이밍하여 해결
  - 외부 라이브러리 레벨 억제 규칙 포함
- 다음 세션은 재시도 로직(지수 백오프) 도입 예정
