# C — 실제 코디세이 API 검증 기록

검증일: 2026-10-23. 대상 코드: b30f5bd의 실제 app.main과 C 채팅 라우터.

## 환경과 방법

- 팀 공용 저장소: innurhap28/cody-B7-1, feature/c-ai-deploy.
- Windows, Python 3.12.15, 프로젝트 requirements-dev.txt 환경.
- 실제 코디세이 https://copa.codyssey.kr/v1, Anthropic 호환, 요청 모델 별칭 claude-sonnet-4. 이번 기록에서 공급자 내부의 실제 모델 버전까지 확인했다고 주장하지 않는다.
- 이전 개인 통합본의 코디세이 설정을 현재 작업 폴더의 로컬 .env에 연결했다. 키·세션 비밀키·.env 내용은 문서나 Git에 넣지 않는다.
- 실제 FastAPI app, 세션, 템플릿, C 코치·검색, B 저장 계층을 사용했다. HTTP는 TestClient로 실행하고 외부 AI 호출은 실제 수행했다.
- 일반 app.db 대신 tmp/ 아래의 별도 SQLite와 임의 생성한 테스트 계정을 사용했다. 기존 사용자 DB는 변경하지 않았다.
- Session HTTPS-only는 TestClient의 로컬 HTTP에 맞춰 해당 프로세스에서 false로 설정했다. 운영 HTTPS 검증은 아니다.

## 결과

| 단계 | 결과 | 실제 AI 처리 시간 |
|---|---|---|
| 로그인 화면·작업 화면 응답 | 200 | AI 호출 없음 |
| 회원가입·로그인 | 201 / 200 | AI 호출 없음 |
| 새 기획 생성 | 201 | AI 호출 없음 |
| 사전 질문 | 200, 빠진 조건 1~2개 질문 | 7.05초 |
| 조건 요약 | 200, ready·confirmed=false | 7.45초 |
| 확인 후 대본 생성 | 200, drafted·버전 1 | 37.20초 |
| 첫 장면 수정 | 200, 버전 2·parent_script_id=1 | 37.98초 |
| 대화·최신 대본·기록 조회 | 200, 성공 대화 4건·대본 2개 버전 | AI 호출 없음 |
| 로그아웃·이후 보호 자원 접근 | 204 / 401 | AI 호출 없음 |

실제 AI 호출은 총 4회이며 오류나 자동 재시도 없이 완료했다. 로컬 결과 report.json의 result는 passed다.

## 생성·수정 확인

- 시나리오: 20대 요리 초보 자취생 대상, 손만 촬영하는 30초 아침 메뉴 릴스.
- 제목: “재료 세 가지로 만드는 자취생 아침”.
- 버전 1은 5개 장면으로 0초부터 30초까지 이어지고 화면·대사·자막·연출·출처가 포함됐다.
- 실제 수정 요청: “첫 장면을 설명 대신 재료를 꺼내는 행동으로 시작해 주세요.”
- 버전 2 첫 장면: 손이 달걀·식빵·버터를 하나씩 꺼내 나란히 내려놓는 행동으로 변경됐다.
- 수정 결과에서 실제 참조한 카드: show-action, mp-intent. 초기 생성은 mp-intent를 참조했다.
- DB 재조회에서 최신 script_id와 두 번째 revision이 일치하고, 성공 대화 4건이 누적된 것을 확인했다.

요청 추적 예시:

- 생성: a74e5008-14ea-4f61-bec6-df08d0ff0fe0
- 수정: ef12ed35-8cdf-4fee-90e5-fb049472143f

## 로컬 증거

Git에서 제외된 tmp/live-chat-2y9wpweq/에 report.json, 단계별 JSON, 격리 app.db가 있다. tmp/live-chat-console.log에는 비밀정보를 제외한 실행 요약이 있다. 원본 .env·DB·세션 쿠키·테스트 계정 비밀번호는 커밋하지 않는다. report는 로컬 증거이며 모든 팀원의 환경에서 동일한 시간이나 결과를 보장하지 않는다.

새 scripts/check_live_chat.py는 명시적인 --live 옵션이 있어야 최대 4회 실제 호출한다. CI나 기본 단위 테스트에서는 실행하지 않는다.

```powershell
Set-Location 'C:\Users\1234v\Documents\Codex\cody-B7-1-c-work'
.\.venv\Scripts\python.exe scripts/check_live_chat.py --live
```

반복 실행 시 실제 사용량이 발생한다. 테스트용 환경 변수를 설정했던 터미널은 닫고 새 터미널에서 실행하여 .env 설정을 사용한다. API 키를 명령행에 넣지 않는다.

## 완료 범위와 남은 검증

완료: 실제 API 연결, 사전 조건 질문·확인, 30초 대본 생성·수정, 출처 반환, SQLite 저장·조회, 로그아웃 후 접근 차단. b30f5bd의 원격 c-unit/foundation push·PR 검사도 모두 통과한 상태를 조회했다.

별도 수행 필요: 실제 브라우저의 클릭·레이아웃·PC/모바일 시각 검사, 다양한 입력에 대한 창작 품질 비교, Linux HTTPS 배포·외부 접속·재시작 후 DB 보존. 이번 실행을 브라우저 시각 검사나 외부 서버 배포 완료로 표시하지 않는다.

테스트 클라이언트의 httpx deprecation 경고가 있었지만 이번 실제 호출과 검증은 통과했다. 의존성 버전은 이 작업에서 변경하지 않았다.

이번 추가 파일·문서는 아직 로컬 변경이며 사용자가 직접 커밋·push한다. .env는 .gitignore에 의해 제외된 것을 확인했다.
