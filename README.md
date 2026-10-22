# STORY / REELS — 인스타 릴스 대본 코치

인스타그램 릴스 대본 작성을 돕는 AI 챗봇 서비스입니다. FastAPI를 기반으로 개발하며, 사용자 인증, 대화 기록 관리, AI 대본 생성 기능을 제공합니다.

## 프로젝트 구조

현재 `main` 브랜치에는 FastAPI 실행 환경과 공통 설정이 등록되어 있습니다. 환경 변수 예시, 의존성 및 공통 요청·응답 규격이 포함되어 있으며, 회원가입, 화면 및 AI 기능은 아직 개발 중입니다.

## 팀 구성

| 담당자 | 역할 | 브랜치 |
|---|---|---|
| A 이송하 | 화면 및 서비스 기획 | `feature/a-reels-ui` |
| B 김시현 (팀장) | 인증, DB, 대화 기록 | `feature/b-accounts-history` |
| C 황승재 | AI 챗봇, 배포 및 최종 통합 | `feature/c-ai-deploy` |

## 개발 현황

- **기본 환경:** FastAPI 시작점 및 공통 설정 등록
- **개발 예정:** 사용자 인증, 화면 구현, 대화 기록 관리, AI 대본 생성
- **통합 및 배포:** 기능별 개발 완료 후 통합 진행

## 로컬 실행

### macOS (Python 3.12 / Terminal)

**1. 가상환경 생성 및 의존성 설치**

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
```

**2. 환경 변수 설정**

```bash
cp -n .env.example .env
```

`.env` 파일을 열고 `SECRET_KEY`에 사용할 키를 생성한다.

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

생성한 값을 `.env` 파일의 `SECRET_KEY`에 입력한다.

**3. 서버 실행**

```bash
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

**4. 실행 확인**

브라우저에서 [http://127.0.0.1:8000/health](http://127.0.0.1:8000/health)에 접속해 `status=ok`를 확인한다.

현재 공통 기반의 `/health` 엔드포인트는 AI API 키 없이 확인할 수 있다.

### Windows (Python 3.12 / PowerShell)

**1. 가상환경 생성 및 의존성 설치**

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

**2. 환경 변수 설정**

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
.\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_hex(32))"
```

생성한 값을 `.env` 파일의 `SECRET_KEY`에 입력한다.

**3. 서버 실행**

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

**4. 실행 확인**

[http://127.0.0.1:8000/health](http://127.0.0.1:8000/health)에 접속해 `status=ok`를 확인한다.

## 통합 순서

main 초기 등록 → develop 생성 → A PR → B PR → C PR → develop 통합 확인 → main PR.
C가 마지막에 라우터·화면·AI·DB를 연결하고 전체 검사 워크플로를 적용한다.
각자 최신 develop을 자신의 브랜치에 반영한 뒤 담당 코드를 적용한다.
제공된 코드 초안을 직접 검토·개선·검증하고 실제 작업과 기여를 기록한다.
.env·DB·.venv는 Git에 올리지 않는다.
