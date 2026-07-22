# AI 기반 Git 커밋 & PR 자동 생성기

`git status` / `git diff` 결과를 수집해 AI API로 넘기고,
커밋 메시지와 Pull Request 초안을 자동으로 생성하는 터미널 도구입니다.

- 모델: Google Gemini (`gemini-3.5-flash-lite`)
- 연동 방식: SDK 없이 REST API 직접 호출
- 실행 환경: Python 3.10 이상, 터미널 전용 (웹 화면 없음)

---

## 1. 설치 및 실행 방법

### 요구 사항
- Python 3.10 이상
- Git

### 가상환경 생성 및 의존성 설치

```bash
git clone <이 저장소 URL>
cd codyssey-academy-b6-2

python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

pip install -r requirements.txt
```

> `python` 이 3.10 미만을 가리킨다면 버전을 명시해서 만드세요.
> ```bash
> python3.12 -m venv .venv
> ```
> 설치 후 `python --version` 으로 3.10 이상인지 확인할 수 있습니다.

의존성은 `requests` 하나뿐입니다. 나머지는 모두 파이썬 표준 라이브러리로 구현했습니다.

```
requests==2.32.3
```

---

## 2. 환경변수(API Key) 설정 방법

API Key는 환경변수로만 관리하며 코드에 하드코딩하지 않습니다.

### 키 발급
[Google AI Studio](https://aistudio.google.com/apikey) 에서 무료로 발급받을 수 있습니다. 신용카드가 필요 없습니다.

### 설정

```bash
export AI_API_KEY="발급받은_키"
```

셸을 새로 열 때마다 유지하려면 `~/.zshrc` 또는 `~/.bashrc` 에 위 줄을 추가하세요.

저장소에는 `.env.example` 템플릿만 포함되어 있습니다. 실제 키가 담긴 `.env` 파일은 `.gitignore` 로 제외되어 커밋되지 않습니다.

키가 설정되지 않은 상태로 실행하면 다음과 같이 안내합니다.

```
[ERROR] AI_API_KEY 환경변수가 설정되지 않았습니다.
       예) export AI_API_KEY="YOUR_KEY"
```

---

## 3. 사용법

```bash
python main.py commit    # 커밋 메시지 생성
python main.py pr        # PR 제목/본문 초안 생성
```

두 명령 모두 Git이 초기화된 프로젝트 루트에서 실행해야 합니다.

### 실행 스크립트 (`./gen`)

가상환경 활성화와 `.env` 로딩을 대신해 주는 스크립트입니다.

```bash
./gen setup     # 가상환경 생성 + 의존성 설치
./gen commit    # 커밋 메시지 생성
./gen pr        # PR 초안 생성
./gen check     # 검증 시나리오 일괄 실행
```

`commit` / `pr` 뒤에 붙인 옵션은 그대로 `main.py` 로 전달됩니다.

```bash
./gen commit --temperature 1.0
```

`.env` 파일이 있으면 자동으로 읽어들이므로 매번 `export` 할 필요가 없습니다.
이미 `AI_API_KEY` 를 export 해 두었다면 그 값이 우선합니다.

### 옵션

| 옵션 | 기본값 | 설명 |
|---|---|---|
| `--model` | `gemini-3.5-flash-lite` | 사용할 모델 ID |
| `--temperature` | `0.3` | 샘플링 무작위성 (0.0 ~ 2.0). 낮을수록 결정적 |
| `--max-tokens` | `1024` | 최대 출력 토큰 수 |
| `--thinking-budget` | 모델에 따라 자동 | 추론에 쓸 토큰 수. `0`이면 추론을 끄고, 음수면 이 설정을 아예 보내지 않음 |
| `--base` | `main` | PR 을 보낼 기준 브랜치 (`pr` 전용) |
| `--safe-mode` | 켜짐 | 민감정보 마스킹 + diff 크기 제한 |
| `--no-safe-mode` | — | safe-mode 해제 (권장하지 않음) |

### 사용 예시

```bash
# 기본 실행
python main.py commit

# PR 초안 생성
python main.py pr

# 더 다양한 표현을 원할 때
python main.py commit --temperature 1.0

# 더 큰 모델로 전환 (thinking-budget 은 알아서 0으로 잡힘)
python main.py commit --model gemini-3.5-flash

# 긴 PR 본문이 잘릴 때
python main.py pr --max-tokens 2048
```

### 두 명령이 보는 diff 가 다릅니다

| 명령 | 보는 대상 | 수집 방법 |
|---|---|---|
| `commit` | 지금 커밋할 내용 | `git diff --staged` |
| `pr` | 브랜치 전체 변경 | `git diff <base>...HEAD` |

커밋 메시지는 인덱스에 올라간 내용을 설명하므로 먼저 `git add` 가 필요합니다.
반면 PR 은 **커밋이 끝난 브랜치**를 설명하는 문서라, 그 시점의 작업 트리는
비어 있는 게 정상입니다. 그래서 `pr` 은 인덱스가 아니라 기준 브랜치와의
차이를 봅니다.

```bash
git checkout -b feature/login
# ... 작업하고 커밋 여러 개 ...
./gen pr                      # main 대비 브랜치 전체를 읽어 초안 생성
./gen pr --base develop       # 기준 브랜치를 바꿀 때
```

기준 브랜치 위에 그대로 서 있거나 `--base` 로 준 브랜치가 없으면
비교 대상이 없으므로 스테이징된 변경으로 넘어갑니다.

### 파라미터가 결과에 주는 영향

| 파라미터 | 값을 낮추면 | 값을 높이면 |
|---|---|---|
| `temperature` | 매번 비슷한 표현, 형식이 안정적 | 표현이 다양해지지만 템플릿을 벗어날 수 있음 |
| `max-tokens` | 응답이 중간에 잘릴 수 있음 | 긴 PR 본문도 온전히 생성되지만 비용 증가 |
| `thinking-budget` | `0`이면 추론 없이 바로 답변 (빠르고 저렴) | 추론 토큰이 출력 예산을 잠식해 답변이 잘릴 수 있음 |

`--thinking-budget` 기본값은 **모델에 따라 자동으로 갈립니다.**
`gemini-3.5-flash-lite` 는 `thinkingConfig` 필드 자체를 거부하기 때문
(`400 Request contains an invalid argument`)입니다.

| 모델 | 기본값 | 의미 |
|---|---|---|
| `gemini-3.5-flash-lite` | `-1` | 이 설정을 요청에 넣지 않음 |
| `gemini-3.5-flash` | `0` | 추론을 끔 |
| 그 밖의 모델 | `-1` | 지원 여부를 모르므로 안전한 쪽 |

직접 지정하면 이 자동 선택보다 우선합니다.

커밋 메시지는 형식 일관성이 중요하므로 `temperature` 기본값을 `0.3` 으로 낮게 잡았습니다.

### 기본 모델을 flash-lite 로 정한 이유

커밋 메시지와 PR 초안은 긴 추론이 필요한 작업이 아닙니다.
diff 를 읽고 정해진 템플릿에 맞춰 요약하는 일이라 상위 모델을 쓸 이유가 적고,
가격 차이는 큽니다 (1M 토큰 기준, 입력 1/5 · 출력 약 1/4).

| 모델 | 입력 | 출력 |
|---|---|---|
| `gemini-3.5-flash` | $1.50 | $9.00 |
| **`gemini-3.5-flash-lite`** (기본) | **$0.30** | **$2.50** |

`gemini-3.5-flash` 로 올릴 때는 추론이 함께 꺼집니다.
이 모델은 답변 전에 먼저 생각하는데, 추론 토큰이 `maxOutputTokens` 예산을
같이 쓰기 때문입니다. `--max-tokens 1024` 로 PR 초안을 요청한 실측 결과:

| 설정 | 추론 토큰 | 답변 토큰 | 결과 |
|---|---|---|---|
| 추론 켜짐 (모델 기본) | 981 | 39 | `finishReason: MAX_TOKENS` — 답변이 잘려 나옴 |
| `--thinking-budget 0` | 0 | 408 | `finishReason: STOP` — 정상 완료 |

```bash
python main.py commit --model gemini-3.5-flash
```

추론을 살리고 싶다면 `--thinking-budget -1` 과 함께
`--max-tokens` 를 넉넉히(예: 3000) 주세요.

---

## 4. 출력 예시

아래는 이 저장소의 초기 구현을 스테이징한 뒤 실제로 실행한 결과입니다.

### 커밋 메시지 생성

```
$ python main.py commit
[INFO] Git status 수집 완료: 12개 파일 변경 감지
[INFO] Git diff 수집 완료: 920줄
[INFO] safe-mode 적용: 11개 항목 마스킹, 1개 파일 제외, 720줄 절삭
[INFO] AI API 요청 중...
[DONE] 커밋 메시지 생성 완료

--- Commit Message ---
feat: Gemini API 기반 AI 커밋 및 PR 메시지 생성기 초기 구현

- `gitgen/ai_client.py`, `gitgen/git_ops.py`, `main.py` 등 핵심 모듈 추가
- SDK 없이 `requests`를 사용해 Gemini REST API 호출 및 예외 처리 구현
- `.env.example`, `.gitignore`, `requirements.txt` 등 프로젝트 기본 환경 설정 파일 추가
------------------------------------------------------------
[INFO] AI API 호출 횟수: 1회
```

### PR 초안 생성

````
$ python main.py pr
[INFO] Git status 수집 완료: 12개 파일 변경 감지
[INFO] Git diff 수집 완료: 920줄
[INFO] safe-mode 적용: 11개 항목 마스킹, 1개 파일 제외, 720줄 절삭
[INFO] 현재 브랜치: main
[INFO] AI API 요청 중...
[DONE] PR 초안 생성 완료

--- PR Title ---
feat: AI 기반 Git 커밋 메시지 및 PR 본문 자동 생성기(gitgen) 초기 구현
------------------------------------------------------------

--- PR Body ---
## Why
- 개발자가 Git 커밋 메시지와 PR 본문을 작성할 때 일관된 템플릿을 유지하고
  작성 시간을 단축할 수 있도록 AI 기반의 자동 생성 도구가 필요합니다.
- 외부 SDK 의존성을 최소화하고 REST API 호출 방식을 직접 구현하여
  요청 생성, 응답 처리, 예외 대응의 전체 흐름을 명확하게 제어하고자 합니다.

## What
- AI API 연동 모듈 구현 (`gitgen/ai_client.py`): Gemini API를 `requests` 로
  호출하는 클라이언트 및 API Key 환경변수 검증 기능 추가
- Git 연동 모듈 구현 (`gitgen/git_ops.py`): `git status` 및 `git diff` 명령을
  실행하여 변경 사항 데이터를 수집하는 기능 구현
- 설정 및 환경 구성 파일 추가: `.env.example`, `.gitignore`, `requirements.txt`

## How to Test
1. 가상환경을 생성하고 의존성 라이브러리를 설치합니다.
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```
2. API Key 환경변수를 설정합니다.
   ```bash
   export AI_API_KEY="발급받은_실제_Gemini_API_키"
   ```
3. 도구를 실행하여 정상적으로 동작하는지 확인합니다.
   ```bash
   python main.py commit
   ```
------------------------------------------------------------
[INFO] AI API 호출 횟수: 1회
````

### 변경은 있으나 스테이징하지 않은 경우

```
$ python main.py commit
[INFO] Git status 수집 완료: 5개 파일 변경 감지
[INFO] 스테이징된 변경이 없습니다. 생성하지 않고 종료합니다.
[INFO] `git add <파일>` 로 커밋할 변경을 올린 뒤 다시 실행하세요.
```

### 출력 토큰이 부족한 경우

```
$ python main.py commit --max-tokens 20
[INFO] AI API 요청 중...
[ERROR] 출력 토큰 한도에 걸려 결과가 중간에 잘렸습니다. --max-tokens 값을 늘려서 다시 실행하세요.
[INFO] AI API 호출 횟수: 1회
```

### 변경 사항이 없는 경우

```
$ python main.py commit
[INFO] Git status 수집 완료: 0개 파일 변경 감지
[INFO] 스테이징된 변경이 없습니다. 생성하지 않고 종료합니다.
```

### API Key 오류

```
$ python main.py commit
[INFO] Git status 수집 완료: 11개 파일 변경 감지
[INFO] Git diff 수집 완료: 920줄
[INFO] safe-mode 적용: 11개 항목 마스킹, 1개 파일 제외, 720줄 절삭
[INFO] AI API 요청 중...
[ERROR] 인증 실패: API Key를 확인하세요. (API key not valid. Please pass a valid API key.)
[INFO] AI API 호출 횟수: 1회
```

---

## 5. 주의사항

### 민감정보

이 도구는 `git diff` 내용을 그대로 AI API로 전송합니다.
또한 Gemini 무료 티어로 보낸 입력은 Google의 제품 개선(학습)에 사용될 수 있습니다.
따라서 `--safe-mode` 를 기본으로 켜 두었습니다.

safe-mode 가 적용하는 규칙:

| 구분 | 내용 |
|---|---|
| 마스킹 | API 키 접두사 (`sk-`, `AIza`, `ghp_`, `xox`-) |
| 마스킹 | `PASSWORD` / `SECRET` / `TOKEN` / `API_KEY` 등이 포함된 환경변수 값 |
| 마스킹 | 이메일 주소 |
| 마스킹 | PEM 개인키 블록 |
| 마스킹 | 32자 이상 hex 문자열 |
| 전송 제한 | 최대 10개 파일 |
| 전송 제한 | 최대 200줄 |

마스킹·절삭이 발생하면 실행 중 `[INFO] safe-mode 적용: ...` 로 알려줍니다.

> ⚠️ 사내 코드나 비공개 저장소에서는 `--no-safe-mode` 를 사용하지 마세요.
> 민감한 코드를 다룬다면 유료 티어로 전환해 데이터가 학습에 쓰이지 않도록 하는 것을 권장합니다.

### 비용 / 요청 횟수

- 1회 실행 = API 호출 1회 입니다. 실행 종료 시 `[INFO] AI API 호출 횟수: 1회` 로 확인할 수 있습니다.
- 무료 티어는 Flash 계열 모델에 적용되며, 일일 요청 한도가 있습니다 (프로젝트별로 다름).
- 유료 전환 시 참고 단가 (1M 토큰 기준):

  | 모델 | 입력 | 출력 |
  |---|---|---|
  | **`gemini-3.5-flash-lite`** (기본) | **$0.30** | **$2.50** |
  | `gemini-3.5-flash` | $1.50 | $9.00 |

  기본값이 더 저렴한 쪽이라 별도 조치는 필요 없습니다.
  품질이 아쉬우면 `--model gemini-3.5-flash` 로 올리세요.
- safe-mode 의 diff 제한(10파일 / 200줄)은 전송 토큰 수를 줄여 비용 절감에도 기여합니다.

### 생성 결과의 성격

생성된 커밋 메시지와 PR 본문은 최종 정답이 아니라 초안입니다.
반드시 사용자가 내용을 검토하고 수정한 뒤 실제 커밋/PR에 적용하세요.

이 도구는 초안 텍스트 출력까지만 담당합니다.
`git commit`, `git push`, GitHub PR 생성 등 저장소를 실제로 변경하는 동작은 수행하지 않습니다.

---

## 6. 프로젝트 구조

```
.
├── gen                     # 실행 스크립트 (setup / commit / pr / check)
├── main.py                 # CLI 진입점 (argparse, commit/pr 서브커맨드)
├── gitgen/
│   ├── git/                # Git 연동
│   │   ├── errors.py       # GitError 예외
│   │   ├── runner.py       # subprocess 로 git 명령 실행
│   │   └── commands.py     # git status / diff / branch 수집
│   ├── sanitizer.py        # safe-mode: 민감정보 마스킹 + diff 제한
│   ├── prompts.py          # 프롬프트 설계 (역할·컨텍스트·양식·제약)
│   ├── ai_client.py        # Gemini REST 호출 + 예외 처리 + 호출 횟수 집계
│   ├── validator.py        # 길이/형식 규칙 검증 및 후처리
│   └── render.py           # 로그 및 결과 블록 출력
├── requirements.txt
├── .env.example
└── README.md
```

### 동작 흐름

```
git 저장소 확인
   ↓
git status / git diff 수집 ────────► 변경 없으면 안내 후 종료
   ↓
safe-mode 마스킹 + 크기 제한
   ↓
프롬프트 구성 (역할 + 컨텍스트 + 출력 양식 + 제약 조건)
   ↓
Gemini REST API 호출 (1회)
   ↓
길이/형식 검증 및 후처리
   ↓
구분선으로 구획을 나눠 터미널 출력
```

### 출력 형식 검증 규칙

| 대상 | 규칙 | 위반 시 |
|---|---|---|
| 커밋 제목 | 50자 이내 권장 | `[WARN]` 경고 |
| 커밋 제목 | 최대 72자 | 절삭 후 `[WARN]` |
| 커밋 제목 | `<type>(<scope>): <subject>` 형식 | `[WARN]` 경고 |
| 커밋 본문 | 본문이 있으면 불릿 1개 이상 | `[WARN]` 경고 |
| PR 제목 | 최대 80자 | 절삭 후 `[WARN]` |
| PR 본문 | `## Why` / `## What` / `## How to Test` 헤더 필수 | 누락 섹션 보완 후 `[WARN]` |
| PR 본문 | 각 섹션 최소 1개 불릿 | 불릿 보완 후 `[WARN]` |

API 호출을 1회로 제한해야 하므로, 규칙 위반은 재생성 대신 후처리 방식으로 보정합니다.
