# C 후속 통합 — 실제 앱의 로그인·접근 제어

## 저장소와 기준

팀 공용 저장소: https://github.com/innurhap28/cody-B7-1

개인 보관용 bidulgiya999/codyssey_work_B7-1-team_final-와 구분한다. 2026-10-23 조회 시 B PR #1, C PR #3, A PR #4는 모두 develop 병합 완료다. develop 3ff2c9021176cf14690084032bca5c4e42619dfd를 로컬 feature/c-ai-deploy에 fast-forward한 뒤 작업했다. 원격 main/develop은 직접 수정하지 않았다.

## 문제와 수정

B 라우터는 실제 app.main에 등록되어 있었으나 SessionMiddleware, APIError 처리기, DB 초기화가 빠져 있었다. 수정 전 실제 앱에 비로그인 GET /api/me, /api/conversations, 대화 상세·기록을 요청하면 500이었다. tmp/main-before-fix.log의 실패 검사로 재현했다.

수정:

- SessionMiddleware: SECRET_KEY, SameSite=Lax, HttpOnly, 8시간, SESSION_HTTPS_ONLY 설정 사용. 키는 코드에 추가하지 않는다.
- lifespan: 등록된 B 모델의 테이블을 create_all로 초기화한다. 기존 스키마 변경용 마이그레이션을 대신하지 않는다. 실패 시 비밀정보 없는 시작 오류를 반환한다.
- APIError: B의 의도한 401/404/409 등 상태 코드와 error/message를 반환한다.
- RequestValidationError: 422 응답에 비밀번호 등 원문 입력을 직렬화하지 않는다.
- SQLAlchemyError: 요청 중 DB 실패를 안전한 503 DB_ERROR로 반환한다.
- 요청 ID를 생성하여 오류 JSON과 X-Request-ID 및 운영 로그를 연결한다. B 라우터의 경로·입출력 필드·DB 스키마는 변경하지 않았다.

## 실제 수행한 검사

새 tests/test_main_access.py는 실제 app.main의 app을 TestClient로 실행하며 실제 lifespan·세션 미들웨어·오류 처리기·B 라우터를 사용한다. 테스트별 별도 앱이나 인증 의존성 대체는 없다. 임시 DB 경로를 검증하고 실제 계정·대화·기록을 저장한다. 외부 AI 키는 빈 값이며 개인 DB를 사용하지 않는다. DB 실패 시나리오 한 곳만 서비스에서 SQLAlchemyError를 발생시키는 대역을 사용한다.

실제 앱 검사 8개 통과(3.522초):

1. lifespan이 users/reels_conversations/reels_turns/reels_scripts 테이블 생성.
2. 비로그인 본인 정보·대화 목록·상세·기록 401.
3. 가입 201, 로그인 200 및 세션 쿠키 속성, 로그인 후 접근 200.
4. 잘못된 비밀번호 401, 비로그인 상태 유지.
5. 잘못된 가입 입력 422, 원문 입력·비밀번호 노출 없음.
6. 소유자는 목록·상세·기록 접근 성공, 타인은 목록 제외 및 상세·기록 404.
7. 동일 클라이언트 로그아웃 204 후 보호 API 401.
8. DB 예외 503, 내부 오류 내용 노출 없음, 오류 JSON과 헤더 요청 ID 일치.

후속 전체 검사: pytest 74 passed, 46 subtests passed, 실패/skip 0, 29.58초. 로그는 tmp/integration-suite-verified.log. A 검사 browser_clients.mjs 9개, workspace_clients.mjs 10개 통과. 실제 브라우저 시각 검사는 아니다.

첫 전체 실행은 B 테스트의 Windows 기본 임시 폴더 접근 권한 및 cp949/UTF-8 해석 차이로 5개 실패했다. B 코드는 변경하지 않고 TEMP/TMP를 작업 폴더의 tmp로 지정하고 PYTHONUTF8=1로 재실행하여 전체 통과했다. 실패 실행을 성공으로 계산하지 않았다.

## 재현 명령 (PowerShell)

가상환경에 requirements-dev.txt가 설치된 프로젝트 루트에서 실행한다. 테스트용 환경 변수는 현재 터미널에만 적용되며 .env를 수정하지 않는다. 종료 후 터미널을 닫고 서버는 별도 터미널에서 실행한다.

```powershell
New-Item -ItemType Directory -Path tmp -Force | Out-Null
$cTemp = (Join-Path (Get-Location) 'tmp')
$env:TEMP = $cTemp
$env:TMP = $cTemp
$env:SHORTFORM_TEST_TMPDIR = $cTemp
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
$env:SECRET_KEY = 'integration-suite-test-only-signing-key-at-least-32'
$env:DATABASE_URL = 'sqlite://'
$env:LLM_API_KEY = ''
.\.venv\Scripts\python.exe tests/test_main_access.py
.\.venv\Scripts\python.exe -m pytest -q
node tests/browser_clients.mjs
node tests/workspace_clients.mjs
```

CI의 C workflow에 실제 앱 검사 실행을 추가했다. 이번 미커밋 수정분의 원격 Actions 결과는 아직 없다.

## 남은 작업

- A 템플릿·정적 파일의 페이지 라우팅 연결.
- C 채팅 API와 B 저장 계층·이론 검색·AI 호출 연결.
- 실제 코디세이 API 호출과 PC·모바일 브라우저 검증.
- Linux HTTPS·영속 DB·외부 접속 검증. 완료 전 main 최종 배포로 간주하지 않는다.
- 로그아웃은 정상 클라이언트 쿠키 제거를 검사한 것이며 탈취된 과거 서명 쿠키의 서버 측 폐기를 구현한 것은 아니다.

사용자 요청에 따라 이번 커밋과 push는 사용자가 직접 수행한다. 변경 파일만 검토·커밋하고, 이미 병합된 PR #3 대신 새 C 통합 PR을 develop 대상으로 생성한다.
