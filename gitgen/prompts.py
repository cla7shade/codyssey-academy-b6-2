"""프롬프트 설계.

이 모듈이 결과물 품질을 좌우한다. 모든 프롬프트는 네 부분으로 구성한다.
  1) 역할 정의   - 모델이 어떤 관점으로 읽어야 하는지
  2) 입력 컨텍스트 - 변경 파일 목록 + diff + 브랜치
  3) 출력 양식   - 지켜야 할 템플릿
  4) 제약 조건   - 길이 규칙과 금지 사항

출력 양식과 제약 조건을 프롬프트에 명시해 두면
validator 가 사후 보정해야 하는 경우가 크게 줄어든다.
"""

COMMIT_TITLE_SOFT_LIMIT = 50
COMMIT_TITLE_HARD_LIMIT = 72
PR_TITLE_LIMIT = 80

# AngularJS 커밋 컨벤션의 표준 type 8종.
COMMIT_TYPES = "feat, fix, docs, style, refactor, perf, test, chore"

# 이 프로젝트의 모듈 구조에서 따온 scope 예시.
SCOPE_EXAMPLES = "git, ai-client, prompts, validator, sanitizer, cli"

_CONTEXT_TEMPLATE = """\
## 변경된 파일 목록 (git status)
```
{status}
```

## 변경 내용 (git diff)
```diff
{diff}
```"""


def _context(status_text, diff_text, branch=None):
    block = _CONTEXT_TEMPLATE.format(status=status_text, diff=diff_text)
    if branch:
        block = f"## 현재 브랜치\n{branch}\n\n" + block
    return block


def build_commit_prompt(status_text, diff_text):
    """커밋 메시지 생성용 프롬프트."""
    return f"""당신은 코드 리뷰 경험이 많은 시니어 개발자입니다.
아래 Git 변경 사항을 읽고 커밋 메시지를 작성하세요.

{_context(status_text, diff_text)}

## 출력 양식
AngularJS 커밋 메시지 컨벤션을 따릅니다. header / body / footer 세 부분이며
body 와 footer 앞에는 반드시 빈 줄을 하나 둡니다.

```
<type>(<scope>): <subject>

<body>

<footer>
```

## 제약 조건

### header (필수)
- type 은 다음 중 하나입니다: {COMMIT_TYPES}
- scope 는 변경된 모듈명입니다. 예: {SCOPE_EXAMPLES}
  변경이 여러 모듈에 걸쳐 하나로 묶기 어려우면 scope 와 괄호를 생략하세요.
- subject 는 첫 글자를 소문자로 쓰고, 끝에 마침표를 붙이지 않습니다.
- subject 는 "무엇을 했다"가 아니라 "무엇을 한다"는 명령형으로 씁니다.
  (예: "추가했음" 이 아니라 "추가")
- header 전체는 {COMMIT_TITLE_SOFT_LIMIT}자 이내를 권장하며
  최대 {COMMIT_TITLE_HARD_LIMIT}자를 넘지 마세요.

### body (선택)
- 변경의 동기와, 이전 동작과 무엇이 달라졌는지를 쓰세요.
- 불릿(`- `)으로 정리하고, 변경된 파일 또는 모듈을 1~3개 언급하세요.

### footer (선택)
- 하위 호환이 깨지는 변경이 있으면 `BREAKING CHANGE: ` 로 시작하는 줄을 넣고
  무엇이 깨지는지와 마이그레이션 방법을 쓰세요.
- 없으면 footer 를 생략하세요.

### 공통
- 실제 diff에 근거해서만 쓰고, 추측한 내용을 넣지 마세요.
- 한국어로 작성하세요. 단, type/scope 와 코드 식별자는 원문 그대로 두세요.
- 설명이나 인사말 없이 커밋 메시지 자체만 출력하세요.
- 전체를 코드 블록(```)으로 감싸지 마세요.
"""


def build_pr_prompt(status_text, diff_text, branch):
    """PR 제목/본문 초안 생성용 프롬프트."""
    return f"""당신은 코드 리뷰 경험이 많은 시니어 개발자입니다.
아래 Git 변경 사항을 읽고 Pull Request 초안을 작성하세요.

{_context(status_text, diff_text, branch)}

## 출력 양식
첫 줄은 PR 제목입니다. 그 다음 줄부터 본문을 아래 템플릿 그대로 작성하세요.

```
<PR 제목 한 줄>

## Why
- 이 변경이 필요한 배경

## What
- 핵심 변경 사항

## How to Test
- 리뷰어가 확인할 방법
```

## 제약 조건
- `## Why`, `## What`, `## How to Test` 세 섹션 헤더를 반드시 모두 포함하세요.
- 각 섹션에 최소 1개 이상의 불릿(`- `)을 작성하세요.
- PR 제목은 최대 {PR_TITLE_LIMIT}자를 넘지 마세요.
- How to Test 에는 실행 가능한 명령이나 확인 절차를 구체적으로 쓰세요.
- 실제 diff에 근거해서만 쓰고, 추측한 내용을 넣지 마세요.
- 한국어로 작성하세요. 단, 섹션 헤더와 코드 식별자는 원문 그대로 두세요.
- 설명이나 인사말 없이 PR 초안 자체만 출력하세요.
- 전체를 코드 블록(```)으로 감싸지 마세요.
"""
