# ADR 0002: 로그 레벨·포맷을 환경변수로 제어

Date: 2026-04-14
Status: Accepted
Feature: 구조적 로깅 도입

## Context

`config.yaml`은 provider 스위치(Slack/NAVER WORKS, Whisper/Claude 등)를 선언하는 정적 설정이다. 반면 로그 레벨과 출력 포맷은 **운영 중에** 바꿔야 하는 값이다. Fly.io에서 장애가 터지면 DEBUG로 잠깐 올려 보고 싶고, 로컬 개발에서는 JSON보다 평문이 읽기 쉽다. `config.yaml`을 건드리면 재배포가 필요하고 기존 provider 스위치 의미와도 결이 다르다.

프로젝트는 이미 시크릿과 URL 같은 환경 의존 값을 `.env`와 Fly secrets로 주입하는 규칙(`${VAR}` 참조)을 갖고 있다(CLAUDE.md).

## Decision

로그 동작은 두 개의 환경변수로만 제어한다.

- `LOG_LEVEL` — `DEBUG|INFO|WARNING|ERROR` (기본 `INFO`)
- `LOG_FORMAT` — `json|plain` (기본 `json`)

`logging_config.setup_logging()`이 기동 시 한 번만 읽고 루트 로거를 구성한다. 변경하려면 Fly secrets 업데이트 후 재시작(`fly deploy` 또는 `fly apps restart`)한다.

## Rationale

- **운영 중 조정 가능성**: Fly에서 `fly secrets set LOG_LEVEL=DEBUG -a meeting-scribe` 한 줄로 디버그 레벨을 올릴 수 있다. config.yaml에 박제하면 PR·머지·배포가 필요하다.
- **환경별 기본값**: 로컬(`.env`)은 `LOG_FORMAT=plain`, 운영은 JSON이 기본. 환경변수는 이미 이런 분기를 위한 장소다.
- **기존 규약과 일관**: 시크릿·환경 의존 값이 env로 주입되는 프로젝트 규칙을 따른다. 새로운 설정 채널을 만들지 않는다.
- **범위가 좁다**: 두 개 스칼라 값이 전부. 더 풍부한 구조(샘플링, per-logger 레벨 등)가 필요해지기 전까지는 env가 충분하다.

## Rejected Alternatives

- **`config.yaml`에 `logging:` 섹션 추가** — provider 스위치와 성격이 다르다(정적 아키텍처 선택 vs 운영 노브). 재배포 없이 바꿀 수 없고 시크릿 파일도 아닌 값을 커밋 대상 YAML에 두면 운영자가 건드리기 망설여진다.
- **CLI 플래그** — `main.py`는 Fly 컨테이너에서 `python main.py`로 기동. 인자 추가는 Dockerfile/fly.toml을 건드려야 하고, 환경변수보다 유연성이 낮다.
- **코드 상수** — 재배포 없이 변경 불가. 기각.
- **동적 리로드(SIGHUP 등)** — 재시작 없이 레벨 바꾸기. 구현 복잡도 대비 이득이 적다. 단일 프로세스 봇이라 재시작 비용이 낮다(Fly 재시작 수 초).
- **per-logger 레벨 설정 노출** — 현재는 루트 레벨 하나로 충분. 노이즈 라이브러리는 코드에서 WARNING으로 고정(slack_bolt, urllib3 등). 필요해지면 `LOG_LEVEL_<module>` 같은 규칙으로 확장 가능.

## Consequences

**긍정**
- 운영 중 디버그 토글이 재배포 없이 가능(`fly secrets set` + 재시작).
- 로컬 개발은 `LOG_FORMAT=plain`으로 가독성 확보, 운영은 JSON 기본으로 기계 파싱 가능.
- 설정 채널이 하나(env)로 통일돼 운영자가 찾을 곳이 명확.

**부정/주의**
- 재시작이 필요하다. 장애 한복판에서 레벨을 올리면 짧은 다운타임이 발생(Fly는 보통 수 초).
- per-logger 세밀 조정이 불가능. 특정 모듈만 DEBUG로 보고 싶으면 코드 수정 필요.
- 기본값이 `json`이므로 아무것도 설정 안 한 로컬 실행자는 한 줄 JSON을 만난다. 문서화(README)로 보완해야 한다.
