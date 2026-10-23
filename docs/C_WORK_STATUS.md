# C 황승재 — AI 기능 1차 작업 및 연결 계획

## 범위와 현재 상태

2026-10-23, 팀장 저장소 innurhap28/cody-B7-1의 develop(51f37838c0a3e899adf07a4414f423ef4e12348c)에서 로컬 feature/c-ai-deploy를 생성했다. 기존 전달 패키지의 C 코드를 검토하여 A/B 없이 검증할 수 있는 서비스 모듈부터 추가했다. 초기 코드는 AI 도구 도움으로 준비했으며 팀원의 직접 기여나 리뷰 완료를 의미하지 않는다.

원격 feature/c-ai-deploy 브랜치와 초기 코드 업로드를 완료했다. 초기 커밋은 74664617a20f441dde8dcdbfbc4eb3ba9d195532, 리뷰 수정 커밋은 b6343e9a93674e25e07f4ed1a0fa7af2201a0811이다. [PR #3](https://github.com/innurhap28/cody-B7-1/pull/3)은 develop에 병합되었다. A PR #4와 B PR #1도 병합되어, 로컬 C 브랜치를 develop의 3ff2c9021176cf14690084032bca5c4e42619dfd까지 fast-forward했다. 초기 및 리뷰 수정 커밋의 Actions 통과와 이번 미커밋 통합 작업의 로컬 검증은 구분한다.

## 이번에 추가한 코드

- app/services/llm.py: 코디세이 Anthropic/OpenAI 호환 요청, 제한 시간, 인증/권한/한도/타임아웃/비정상 응답 구분. 실제 키를 저장하지 않는다.
- app/services/shortform/coach.py: 제작 조건 추출·보존, 누락 질문 최대 2개, 요약 확인 후 생성, 수정 및 응답 검증.
- app/services/shortform/knowledge.py: 이용 가능한 카드 검색·출처 구성, 미확인 이용 조건·미검토 카드 제외.
- app/services/shortform/research.py: 연구 질문을 검증된 결과와 구분해 전달.
- app/services/shortform/structures.py: 제작 조건에 따른 구조 제안. 미완성 조건에 구조를 미리 강제하지 않는다.
- app/data/shortform/: 원문 후보 15종 중 활성 자료 12종, 한국어 개념 카드 21개, 연구 질문과 출처·이용 조건. 모델 가중치 학습이나 PDF 전체 수집이 아니다.
- scripts/check_knowledge.py: 키·서버·DB 없이 이론 검색 확인.
- tests/test_core.py, test_gateway.py, test_structures.py, async_runner.py: C 단위 검사와 공급자 HTTP 대역.
- .github/workflows/c-ai-unit-tests.yml: 기존 기반 CI를 수정하지 않고 추가한 독립 C 검사.

## 충돌 방지 경계

1차 PR에서는 기존 develop 파일을 수정하지 않았다. 후속 통합 작업에서는 합의한 공통 main.py의 세션·오류 처리·DB 초기화를 연결했다. config.py, 공통 schemas.py, A의 템플릿·JS/CSS, B의 인증·DB·모델·store.py는 변경하지 않았다. 이후 A/B가 공통 파일을 수정하면 다시 비교해야 한다.

현재 실제 앱에는 A 페이지·정적 파일, B 인증·대화 라우터, C 채팅 라우터가 연결되어 있다. /는 로그인 여부에 따라 로그인 페이지로 이동하거나 작업 화면을 표시하며 /health는 JSON을 유지한다. 세션·DB 초기화·지식 검색·오류 처리를 연결했다. [세션 통합 검증](C_AUTH_INTEGRATION.md), [화면·채팅 통합](C_SCREEN_CHAT_INTEGRATION.md), [실제 코디세이 검증](C_LIVE_VERIFICATION.md)에 단계별 범위를 기록했다. 실제 API 검증까지 완료했으며 브라우저 시각·외부 배포는 별도다.

## 직접 수행한 검증

환경: Windows PowerShell, Python 3.12.15, requirements-dev.txt 설치.

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

초기 로컬 실행: 53개 실행, 실패 0, skip 0, 0.214초. 로그는 로컬 tmp/c-tests.log에 있으며 Git에 포함하지 않는다. 모의 공급자 응답을 사용했다. 실제 코디세이 요청·화면·DB 저장·외부 배포는 이번 범위에서 검증하지 않았다. 초기 커밋의 원격 [c-unit](https://github.com/innurhap28/cody-B7-1/actions/runs/39920535993/job/120304407824) 및 [foundation](https://github.com/innurhap28/cody-B7-1/actions/runs/39920535991/job/120304407414) 검사 통과를 확인했다.

### 리뷰 반영: 대본 생성 후 변경 없는 메시지

- action=message, intent=brief, 제작 조건이 완성된 상태에서 변경 없는 메시지까지 ready로 전환하고 confirmed를 해제하는 문제를 회귀 검사로 재현했다.
- drafted에서 실제 제작 조건이 바뀌지 않으면 drafted·confirmed를 보존한다. 빈 패치뿐 아니라 기존 값의 반복도 변경 없음으로 판정한다.
- 응답 필드나 공통 스키마는 변경하지 않았다. script=null은 새 대본 생성이 없다는 뜻이며 B 저장 계층은 기존 최신 대본을 유지한다.
- 조건 변경으로 완성된 기획은 ready에서 다시 확인받고, 필수 조건이 지워지면 briefing에서 질문한다.
- 회귀 검사 4개를 추가했다: 변경 없음(3종 패치), 실제 길이 변경, 필수 조건 제거, 변경 없는 메시지 이후 대본 수정 가능 여부. 기존 설명 질문의 drafted 유지 검사도 유지한다.
- 리뷰 수정 후 로컬 검사: 57개 통과, 실패 0, skip 0, 0.198초. tmp/review-after-fix.log에 기록했다. 해당 수정은 b6343e9로 업로드되어 c-unit/foundation 통과 후 PR #3으로 병합되었다.

### 후속 통합: 실제 앱의 세션·오류 처리·DB 초기화

- 실제 app.main에서 비로그인 보호 API가 500으로 실패하는 문제를 재현하고 401 JSON 응답으로 수정했다.
- 실제 app.main과 임시 SQLite로 검사 8개 통과. 별도 앱·테스트용 미들웨어·수동 create_all로 대체하지 않았다.
- 전체 pytest 74개 및 하위 검사 46개 통과, 실패/skip 0. A DOM 대역 검사 9개 및 작업 화면 검사 10개 통과.
- 이 세션 연결은 사용자가 4441e7b로 커밋·push하여 PR #5를 생성했고 원격 c-unit/foundation 검사가 통과했다. 작업 시작 시 PR #5는 아직 리뷰 중이었다.

### 후속 통합: A 화면과 C 채팅 API

- app/main.py에 로그인·가입·작업 화면과 정적 파일을 연결하고 app/routers/shortform.py를 추가했다.
- B 저장 함수와 C 코치를 연결하여 질문·확인·생성·수정·실패 기록을 처리한다. A/B 코드와 공통 스키마는 변경하지 않았다.
- 실제 앱 검사 16개를 포함한 pytest 82개 및 하위 검사 46개 통과, 실패/skip 0, 46.79초. Node DOM 검사 19개 통과. AI 호출은 대역이며 실제 공급자 호출은 미검증이다.
- 사용자가 b30f5bd로 커밋·push했으며 해당 커밋의 원격 c-unit/foundation 검사 4개도 통과했다. PR #5의 추가 범위로 리뷰받는다.

### 후속 검증: 실제 코디세이 호출

- 현재 작업 폴더의 로컬 .env에 기존 코디세이 설정을 연결하고 Git 제외를 확인했다.
- 실제 API 4회로 사전 질문·조건 요약·30초 5장면 대본 생성·첫 장면 수정에 성공했다. 성공 대화 4건과 대본 2개 버전을 격리 SQLite에 저장·조회했고 로그아웃 후 401도 확인했다.
- 요청 모델 별칭은 claude-sonnet-4, Anthropic 호환이다. .env·실제 키·DB는 업로드하지 않는다.
- 재현 스크립트 scripts/check_live_chat.py와 기록 문서를 추가했다. 명시적인 --live 실행만 실제 요청하며 CI에서는 호출하지 않는다. 이번 파일은 사용자 커밋 전 로컬 변경이다.

키 없는 검색 확인:

```powershell
.\.venv\Scripts\python.exe scripts/check_knowledge.py --query '몽타주와 연속 편집'
```

## 연결 이후 남은 순서

1. 추가 실제 검증 스크립트·문서를 사용자가 검토·커밋·push한다.
2. 실제 브라우저 PC·모바일에서 가입·로그인·기획·생성·수정·출처·기록을 확인한다.
3. 팀 리뷰 후 develop에 병합한다. Linux HTTPS·영속 DB·외부 접속 검증은 별도다.

## 리뷰 의견 반영 및 추가 업로드

이 폴더에서 git remote -v가 팀장 저장소를 가리키는지 확인한다. GitHub Collaborator 초대 수락과 연결 앱의 저장소 쓰기 권한은 별개일 수 있다. 토큰을 소스나 터미널 명령에 직접 넣지 않는다.

```powershell
git branch --show-current
git status
git diff --cached --stat
git diff --cached
git add scripts/check_live_chat.py docs/C_LIVE_VERIFICATION.md docs/C_WORK_STATUS.md docs/C_SCREEN_CHAT_INTEGRATION.md
git commit -m "test: 실제 코디세이 생성과 수정 검증 기록 추가"
git push
```

로컬 작성자 설정과 origin/feature/c-ai-deploy 추적 연결이 완료되어 있다. PR #3은 이미 병합되었다. PR #5의 현재 상태에 따라 기존 PR에 포함하거나 새 PR을 생성한다. 다른 팀원 작성자 정보로 커밋하지 않는다.

GitHub PR의 base는 develop, compare는 feature/c-ai-deploy로 한다. 화면·채팅 연결과 실제 API 검증 결과를 밝히고 브라우저 시각·배포 미검증 항목을 남긴다.
