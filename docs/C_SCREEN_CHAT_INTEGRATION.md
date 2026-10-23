# C — A 화면 및 채팅 API 연결

## 작업 범위

팀 공용 innurhap28/cody-B7-1의 feature/c-ai-deploy에서 PR #5의 세션 연결 커밋 4441e7b 위에 이어서 작업했다. 작업 시작 시 PR #5는 develop 대상의 열린 PR이었다. 같은 브랜치에 push하면 이번 변경도 PR #5에 포함되므로 리뷰어에게 추가 범위를 알린다. 이후 PR #5가 병합됐다면 최신 develop을 반영하고 별도 PR로 진행한다.

변경:

- app/main.py: 기존 세션·오류 처리·DB 초기화를 유지하고 지식 검색 초기화, 정적 파일 마운트, A 템플릿 페이지와 C 라우터를 연결했다.
- app/routers/shortform.py: 인증 → B begin_turn → C 이론 검색·기획·AI 처리 → B complete_turn → 응답. 실패는 fail_turn으로 기록하고 마지막 성공 기획·대본을 유지한다.
- tests/test_main_access.py: 기존 실제 앱 검사 8개에 화면·채팅 흐름 검사 8개를 추가했다. 기존 CI의 실제 앱 실행 단계가 이 파일을 실행하므로 새 검사도 포함된다.

A 템플릿·JS·CSS와 B 인증·DB·모델·store.py 및 공통 schemas.py는 수정하지 않았다. 기존 실제 엔드포인트와 A가 사용하는 conversation_id/expected_version/action/message/base_script_id 규격을 따른다.

## 화면 주소

| 주소 | 동작 |
|---|---|
| GET / | 비로그인 시 /login으로 303, 로그인 시 A workspace.html |
| GET /login | A 로그인 화면. 로그인 상태이면 /로 303 |
| GET /signup | A 가입 화면. 로그인 상태이면 /로 303 |
| GET /history | 기존 작업 화면 /로 이동 |
| GET /static/... | A CSS와 JS |
| GET /health | 프로세스 상태 JSON. 실제 AI 연결을 보증하지 않음 |

기존 /의 JSON 안내를 로그인 기반 HTML 화면으로 바꿨다. 상태 확인에는 /health를 사용한다.

## 채팅 API 규격

POST /api/chat. 로그인 쿠키 필요. 사용자의 ID는 서버 인증에서 결정한다.

```json
{"conversation_id":1,"expected_version":0,"action":"message","message":"20대 자취생을 위한 30초 릴스"}
```

- action=message: 제작 조건 정리·요약·이론 설명. 누락 질문 최대 2개.
- action=generate: 조건이 완성되어 ready 상태일 때 사용자 확인으로 대본 생성.
- action=revise: drafted 상태에서 최신 base_script_id를 전달하여 대본 수정.
- 응답: chat_id/conversation_id/version/request_id/phase/reply_type/answer/brief/missing_fields/follow_up_questions/script/references.
- 수정하지 않은 메시지에서 script=null은 새 대본이 없다는 뜻이다. B 저장 계층의 기존 latest_script는 유지된다.
- 401 로그인 필요, 404 타인/없는 대화, 409 버전·대본 충돌, 422 잘못된 입력, 429 한도, 502 AI 오류, 503 저장 실패, 504 시간 초과.
- request_received → ai_call_start → ai_call_success 또는 ai_call_fail → db_save_success/db_save_fail을 요청 ID로 추적한다. 메시지 본문과 키는 이벤트 로그에 기록하지 않는다.

## 검증 범위

실제 app.main, 실제 세션·B 저장 계층·SQLite를 사용했다. TestClient가 실행한 lifespan에서 DB와 지식 검색을 초기화한다. AI 호출만 AsyncMock 응답으로 대체했으며 실제 코디세이에 접속하지 않았다.

추가한 검사:

1. 가입/로그인/작업 화면 및 정적 파일 응답, 인증 상태에 따른 페이지 이동.
2. 비로그인·빈 입력·타인 채팅은 AI 호출 전에 차단.
3. 사전 질문 → 미완성 조건에서 생성 차단 → 요약 → 확인 후 생성 → 고마워 → 수정. 실제 B 저장 결과·대본 버전·출처·기록 확인.
4. 다른 대화방의 조건·기록이 AI 문맥에 섞이지 않음.
5. timeout/401/403/429/일반 공급자 오류/잘못된 JSON: 마지막 성공 조건·대본·버전을 보존하고 처리 표시를 해제. 실패 턴은 후속 AI 문맥에서 제외.
6. DB 저장 실패: 503, 실패 기록, 처리 표시 해제 및 버전 보존.
7. 오래된 version은 409이며 AI 재호출 없음.
8. 요청·AI·DB 이벤트의 요청 ID 연결과 민감한 질문·키의 로그 제외.

테스트 명령과 Windows 임시 폴더/UTF-8 설정은 C_AUTH_INTEGRATION.md를 따른다. 브라우저 시각 검사·실제 모델 품질·외부 배포는 자동 검사의 범위가 아니다.

최종 로컬 전체 실행: pytest 82 passed, 46 subtests passed, 실패/skip 0, 46.79초. 로그는 tmp/screen-chat-suite.log다. 앞선 실제 앱 16개 직접 실행도 통과했으며, 마지막 전체 실행에는 기존 대본 보존까지 보강한 실패 검사가 포함된다. Node 검사 browser_clients.mjs 9개와 workspace_clients.mjs 10개도 통과했다. 이번 미커밋 코드의 GitHub Actions 결과는 아직 없다.

## 로컬 실행

프로젝트 루트는 C:\Users\1234v\Documents\Codex\cody-B7-1-c-work다. 이전 개인 통합본의 바탕화면 폴더와 구분한다.

처음 화면 연결 시 이 폴더에는 .env가 없었으나, 후속 실제 API 검증에서 이전 개인 통합본의 설정을 로컬 .env로 연결했다. .env는 Git에서 제외한다. 다른 PC에서 처음 실행한다면 .env.example을 복사한 뒤 로컬에서 SECRET_KEY와 LLM_API_KEY를 설정한다. 기존 .env가 있다면 덮어쓰지 않는다. 키를 Git/PR/화면 캡처에 포함하지 않는다.

```powershell
Set-Location 'C:\Users\1234v\Documents\Codex\cody-B7-1-c-work'
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
.\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_hex(32))"
```

출력 문자열을 .env의 SECRET_KEY에 넣는다. 코디세이 키는 LLM_API_KEY에 직접 입력하고, 기존 키의 호환 방식에 따라 LLM_API_STYLE=anthropic, LLM_BASE_URL=https://copa.codyssey.kr/v1, LLM_MODEL=claude-sonnet-4 설정을 확인한다. 지원 모델은 공급자 계정 설정을 기준으로 하며 테스트 대역 통과가 실제 권한을 보증하지 않는다.

테스트용 환경 변수를 설정했던 터미널은 닫고 새 터미널에서 실행한다.

```powershell
Set-Location 'C:\Users\1234v\Documents\Codex\cody-B7-1-c-work'
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

http://127.0.0.1:8000/login 에서 가입·로그인 후 새 기획을 만든다. 이론 자료 출처 확인과 실제 생성·수정·저장, PC·모바일 화면은 별도로 확인해야 한다. API 키를 설정하지 않으면 안전한 오류를 안내하며 테스트 대본을 실제 AI 결과로 보여주지 않는다.

## 커밋 및 후속 작업

사용자가 화면 연결을 b30f5bd로 커밋·push했다. 이후 [실제 API 검증](C_LIVE_VERIFICATION.md)에서 코디세이 호출 4회와 생성·수정·저장을 확인했다. 브라우저 시각 확인·Linux HTTPS 배포는 별도다. 추가 검증 스크립트와 문서는 사용자 커밋을 기다리는 로컬 변경이다.
