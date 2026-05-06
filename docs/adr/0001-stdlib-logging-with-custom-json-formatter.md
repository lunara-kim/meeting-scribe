# ADR 0001: stdlib logging + 자체 JSON formatter

Date: 2026-04-14
Status: Accepted
Feature: 구조적 로깅 도입

## Context

이전까지 meeting-scribe는 모든 관측 포인트를 `print()`로 찍고 있었다. 22곳이 이모지 섞인 한글 문자열로 stdout에 나가고, Fly.io 로그 수집기는 그걸 비구조 텍스트로 받아 저장했다. 장애가 나면 Fly 콘솔에서 눈으로 grep하는 수밖에 없었고, 스택트레이스는 `print(f"❌ {e}")` 패턴 탓에 유실됐다.

프로젝트는 외부 의존성을 얇게 유지해왔다(`requirements.txt` 20줄 미만). Python 3.11+만 지원한다. Fly.io는 stdout을 줄 단위로 수집하므로 한 줄 JSON이면 구조화 파싱·쿼리가 가능하다.

## Decision

Python 표준 라이브러리 `logging`을 채택하고, 자체 `JsonFormatter`를 `logging_config.py`에 구현해 한 줄 JSON으로 출력한다. 각 모듈은 `logger = logging.getLogger(__name__)`로 모듈별 로거를 얻고, 컨텍스트는 `extra={"key": value, ...}`로 구조화 주입한다. 에러는 `logger.exception()`으로 기록해 스택트레이스를 JSON `exc` 필드에 포함시킨다.

## Rationale

- **의존성 0**: `python-json-logger`나 `structlog`, `loguru`를 쓰지 않아도 30줄짜리 `JsonFormatter`로 요구 스펙이 전부 충족된다. 단순 포맷터 하나 때문에 신규 의존성을 추가하면 프로젝트 기조(얇은 requirements)와 어긋난다.
- **기계 파싱 가능**: `extra`로 넘긴 필드는 LogRecord 속성으로 붙고 formatter가 JSON key로 승격한다. f-string 메시지 포매팅과 달리 Fly 로그 쿼리에서 `file_id`, `attempt`, `bytes` 같은 필드로 바로 필터링할 수 있다.
- **점진 이전이 아닌 일괄 교체**: 22곳뿐이라 부분 이전은 스타일 혼재만 낳는다.

## Rejected Alternatives

- **`python-json-logger`** — 사실상 표준이고 편하지만, 30줄로 해결될 일에 의존성 추가는 과하다. formatter가 복잡해지면 그때 재검토.
- **`structlog`** — 강력한 구조화 로거지만 API가 stdlib과 달라 학습 비용이 있고, 외부 라이브러리(slack_bolt, flask 등)와 핸들러 체인을 맞추는 추가 설정이 필요하다.
- **`loguru`** — DX는 최고지만 stdlib 로거 생태계(외부 라이브러리가 내보내는 로그)와 호환을 맞추려면 `InterceptHandler`를 깔아야 하고, 그러면 결국 stdlib을 거치는 구조라 이득이 크지 않다.
- **`print()` 유지 + stdout 파싱** — Fly 쪽 수집기에서 정규식으로 뽑는 식. 메시지 포맷 변경마다 파서가 깨져 장기적으로 취약하다.
- **메시지 문자열에 컨텍스트 포매팅** — `logger.info(f"download ok, bytes={n}, attempt={a}")` 식. 읽기는 쉽지만 JSON 쿼리 불가. 구조화의 의의가 사라진다.

## Consequences

**긍정**
- Fly 로그에서 `level`, `logger`, 커스텀 필드로 필터/집계 가능. 장애 분석 시간이 줄어든다.
- 에러 경로에서 스택트레이스가 항상 남는다(`logger.exception()`).
- 외부 의존성 추가 없음. 빌드·보안 취약점 표면이 늘지 않는다.
- 테스트에서 caplog로 로그 검증이 가능해진다.

**부정/주의**
- LogRecord 예약 속성(`filename`, `module`, `name`, `levelname` 등)은 `extra`에 쓸 수 없다. 실수 시 `KeyError: Attempt to overwrite ...`로 런타임 실패. 네이밍 규칙(예: `audio_filename`)으로 회피.
- 로컬 개발에서 JSON 한 줄은 가독성이 떨어진다. `LOG_FORMAT=plain` 스위치(ADR 0002)로 완화.
- 포맷터를 직접 유지보수해야 한다. 스키마 진화(예: trace_id 추가)가 생기면 이 프로젝트에서 코드를 건드려야 한다.
