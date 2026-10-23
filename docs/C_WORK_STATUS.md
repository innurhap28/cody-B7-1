# C 황승재 — AI 기능 1차 작업 및 연결 계획

## 범위와 현재 상태

2026-10-23, 팀장 저장소 innurhap28/cody-B7-1의 develop(51f37838c0a3e899adf07a4414f423ef4e12348c)에서 로컬 feature/c-ai-deploy를 생성했다. 기존 전달 패키지의 C 코드를 검토하여 A/B 없이 검증할 수 있는 서비스 모듈부터 추가했다. 초기 코드는 AI 도구 도움으로 준비했으며 팀원의 직접 기여나 리뷰 완료를 의미하지 않는다.

원격 feature/c-ai-deploy 브랜치 생성과 초기 코드 업로드를 완료했다. 초기 커밋은 74664617a20f441dde8dcdbfbc4eb3ba9d195532이며, [PR #3](https://github.com/innurhap28/cody-B7-1/pull/3)을 develop 대상으로 열어 리뷰 중이다. 해당 초기 커밋의 GitHub Actions c-unit 및 foundation 검사가 통과했다. 연결 도구 권한 오류 이후 본인 PC의 Git으로 업로드했으며, 초기 커밋의 통과 결과가 이후 수정 커밋까지 보증하는 것은 아니다.

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

기존 develop 파일은 하나도 수정하지 않았다. main.py, config.py, 공통 schemas.py, README, 기존 CI는 유지한다. A의 템플릿·JS/CSS와 B의 인증·DB·모델·store.py도 추가·변경하지 않는다. 현재 B PR #1의 변경 14개 경로와 이번 C 추가 경로는 겹치지 않는다. 이후 A/B가 새로운 공통 파일을 수정하면 다시 비교해야 하며 미래의 충돌이 없음을 보장하는 것은 아니다.

채팅 라우터 app/routers/shortform.py 및 main.py의 최종 연결은 B 저장 계층과 A 화면 준비 후 별도 변경으로 진행한다. 지금 서버의 / 및 /health는 기존 기반 기능이며 로그인·AI 채팅 전체 화면은 아직 이 브랜치에 연결되지 않는다.

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
- 리뷰 수정 후 로컬 전체 검사: 57개 통과, 실패 0, skip 0, 0.198초. tmp/review-after-fix.log에 기록했다. 수정분은 로컬 작업 트리에 있으며 초기 원격 Actions 결과와 구분한다. 추가 커밋을 push한 뒤 새 Actions 결과를 확인해야 한다.

키 없는 검색 확인:

```powershell
.\.venv\Scripts\python.exe scripts/check_knowledge.py --query '몽타주와 연속 편집'
```

## A/B 병합 후 순서

1. 작업을 커밋한 뒤 git fetch origin, C 브랜치에서 git merge origin/develop.
2. B 인증 의존성, begin_turn/complete_turn/fail_turn, 사용자 소유권 및 version 규격 확인. 공통 API/DB/스키마 변경은 B/A와 협의.
3. C 채팅 라우터를 추가하고 B 저장 계층 및 AI 서비스 연결.
4. A 화면과 연결하여 main.py의 라우터·세션·초기화·오류·로그 통합. 기존 main.py를 무조건 덮어쓰지 않고 diff로 검토.
5. 인증, 대화별 문맥, 생성·수정·저장, 실패 상태의 통합 테스트.
6. 본인 로컬 .env에 키 설정 후 실제 코디세이 시연. 키는 Git/로그/PR에 포함하지 않음.
7. 본인 브랜치 → develop PR, 리뷰 후 병합. Linux 배포·외부 접속 검증은 별도.

## 리뷰 의견 반영 및 추가 업로드

이 폴더에서 git remote -v가 팀장 저장소를 가리키는지 확인한다. GitHub Collaborator 초대 수락과 연결 앱의 저장소 쓰기 권한은 별개일 수 있다. 토큰을 소스나 터미널 명령에 직접 넣지 않는다.

```powershell
git branch --show-current
git status
git diff --cached --stat
git diff --cached
git add app/services/shortform/coach.py tests/test_core.py docs/C_WORK_STATUS.md
git commit -m "fix: 기획 변경 없는 메시지에서 대본 상태 유지"
git push
```

로컬 작성자 설정과 origin/feature/c-ai-deploy 추적 연결이 완료되어 있다. 같은 브랜치에 추가 커밋을 push하면 기존 PR #3에 반영된다. 다른 팀원 작성자 정보로 커밋하지 않는다.

GitHub PR의 base는 develop, compare는 feature/c-ai-deploy로 한다. 초기 C 모듈 PR임을 밝히고 전체 채팅 연결·실제 AI·배포 미검증 항목을 남긴다.
