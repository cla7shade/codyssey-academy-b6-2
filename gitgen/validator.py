"""생성 결과가 길이/형식 규칙을 만족하도록 검증하고 다듬는다.

재생성 대신 후처리 방식을 쓴다. 1회 실행당 API 호출을 1회로
제한해야 하므로, 규칙 위반은 다시 물어보지 않고 이 자리에서 고친다.
검증 결과는 warnings 로 모아 사용자에게 무엇이 보정됐는지 알린다.
"""

import re

from .prompts import (
    COMMIT_TITLE_HARD_LIMIT,
    COMMIT_TITLE_SOFT_LIMIT,
    COMMIT_TYPES,
    PR_TITLE_LIMIT,
)

# AngularJS 컨벤션의 header: type(scope): subject
# scope 와 괄호는 생략할 수 있다.
COMMIT_HEADER = re.compile(
    r"^(?P<type>[a-z]+)(?:\((?P<scope>[^)]+)\))?: (?P<subject>.+)$"
)
VALID_TYPES = {t.strip() for t in COMMIT_TYPES.split(",")}

PR_SECTIONS = ["## Why", "## What", "## How to Test"]
PLACEHOLDER = "- (내용을 직접 채워주세요)"

# '- ', '* ', '1. ', '2) ' 를 모두 목록 항목으로 인정한다.
LIST_ITEM = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+\S")


class Result:
    """다듬어진 텍스트와 보정 내역."""

    def __init__(self, text, warnings):
        self.text = text
        self.warnings = warnings


def strip_code_fence(text):
    """모델이 전체를 ``` 로 감싼 경우 바깥 펜스만 제거한다."""
    lines = text.strip().splitlines()
    if len(lines) >= 2 and lines[0].startswith("```") and lines[-1].strip() == "```":
        lines = lines[1:-1]
    return "\n".join(lines).strip()


def _truncate(line, limit):
    """말줄임 없이 limit 자로 자른다. 단어 중간을 피해 공백에서 끊는다."""
    if len(line) <= limit:
        return line
    cut = line[:limit]
    if " " in cut[limit // 2:]:
        cut = cut[:cut.rfind(" ")]
    return cut.rstrip()


def _check_header(title):
    """AngularJS 컨벤션 위반을 경고로 모은다.

    header 는 자동으로 고치지 않는다. type 이나 scope 를 코드가 임의로
    지어내면 diff 와 맞지 않는 메시지가 되기 때문에, 사람이 판단하도록
    무엇이 어긋났는지만 알린다.
    """
    match = COMMIT_HEADER.match(title)
    if not match:
        return [
            "커밋 제목이 '<type>(<scope>): <subject>' 형식이 아닙니다. "
            f"사용 가능한 type: {COMMIT_TYPES}"
        ]

    issues = []
    commit_type = match.group("type")
    subject = match.group("subject")

    if commit_type not in VALID_TYPES:
        issues.append(
            f"'{commit_type}' 은 표준 type 이 아닙니다. 사용 가능: {COMMIT_TYPES}"
        )
    if subject.endswith("."):
        issues.append("커밋 제목 끝에 마침표를 쓰지 않습니다.")

    # subject 첫 글자 소문자 규칙은 검사하지 않는다.
    # 'Gemini REST 클라이언트 추가' 처럼 고유명사나 코드 식별자로 시작하는
    # 경우가 많은데, 프롬프트가 식별자를 원문 그대로 두라고 지시하고 있어
    # 기계적으로 검사하면 정상 메시지를 계속 경고하게 된다.

    return issues


def _check_body(body_lines):
    """본문을 포함한 경우의 요약 품질 최소 기준을 확인한다.

    본문이 있다면 '변경된 파일/모듈 언급' 또는 '핵심 변경 불릿' 중
    하나는 있어야 읽는 사람이 무엇이 바뀌었는지 알 수 있다.
    본문은 선택 사항이므로, 아예 없으면 검사하지 않는다.

    header 와 마찬가지로 자동으로 고치지 않는다. 없는 내용을 코드가
    지어낼 수는 없으므로 무엇이 부족한지만 알린다.
    """
    body = [line for line in body_lines if line.strip()]
    if not body:
        return []

    if any(LIST_ITEM.match(line) for line in body):
        return []

    return [
        "커밋 본문에 불릿이 없습니다. 변경된 파일/모듈이나 "
        "핵심 변경 사항을 `- ` 불릿으로 정리하세요."
    ]


def validate_commit(raw):
    """커밋 메시지: 제목 1줄 필수, 제목 길이 규칙 적용."""
    warnings = []
    text = strip_code_fence(raw)

    lines = text.splitlines()
    if not lines or not lines[0].strip():
        return Result(text, ["커밋 제목을 찾을 수 없습니다. 결과를 직접 확인하세요."])

    title = lines[0].strip()
    body = lines[1:]

    warnings.extend(_check_header(title))

    if len(title) > COMMIT_TITLE_HARD_LIMIT:
        warnings.append(
            f"커밋 제목이 {COMMIT_TITLE_HARD_LIMIT}자를 초과하여 절삭했습니다."
        )
        title = _truncate(title, COMMIT_TITLE_HARD_LIMIT)
    elif len(title) > COMMIT_TITLE_SOFT_LIMIT:
        warnings.append(
            f"커밋 제목이 권장 길이({COMMIT_TITLE_SOFT_LIMIT}자)를 넘습니다. "
            f"현재 {len(title)}자."
        )

    warnings.extend(_check_body(body))

    return Result("\n".join([title] + body).strip(), warnings)


def _split_sections(body_lines):
    """본문을 섹션 헤더 기준으로 나눈다. 헤더 표기 흔들림을 흡수한다."""
    sections = {}
    order = []
    current = None
    for line in body_lines:
        matched = None
        for section in PR_SECTIONS:
            # '## Why (변경 배경)' 처럼 뒤에 설명이 붙어도 같은 섹션으로 본다.
            pattern = r"^\s*#{1,4}\s*" + re.escape(section.lstrip("# ")) + r"\b"
            if re.match(pattern, line, flags=re.IGNORECASE):
                matched = section
                break
        if matched:
            current = matched
            sections[current] = []
            order.append(current)
        elif current:
            sections[current].append(line)
    return sections, order


def _bulletize(lines):
    """목록이 하나도 없는 섹션의 산문을 불릿으로 바꾼다.

    코드 블록 안은 건드리지 않는다. ```bash 같은 줄에 '- ' 를 붙이면
    코드 블록이 깨져서 오히려 읽기 어려워진다.
    """
    result = []
    in_fence = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            result.append(line)
        elif in_fence or not stripped:
            result.append(line)
        else:
            result.append(f"- {stripped}")

    if not any(LIST_ITEM.match(line) for line in result):
        return [PLACEHOLDER]
    return result


def validate_pr(raw):
    """PR: 제목 길이, 세 섹션 헤더 존재, 섹션별 불릿 1개 이상."""
    warnings = []
    text = strip_code_fence(raw)

    lines = text.splitlines()
    if not lines or not lines[0].strip():
        return Result(text, ["PR 제목을 찾을 수 없습니다. 결과를 직접 확인하세요."])

    title = lines[0].strip()
    if len(title) > PR_TITLE_LIMIT:
        warnings.append(f"PR 제목이 {PR_TITLE_LIMIT}자를 초과하여 절삭했습니다.")
        title = _truncate(title, PR_TITLE_LIMIT)

    sections, _order = _split_sections(lines[1:])

    rebuilt = []
    for section in PR_SECTIONS:
        content = sections.get(section)
        if content is None:
            warnings.append(f"{section} 섹션이 누락되어 보완했습니다.")
            content = [PLACEHOLDER]
        else:
            if not any(LIST_ITEM.match(line) for line in content):
                warnings.append(f"{section} 섹션에 불릿이 없어 보완했습니다.")
                content = _bulletize(content)

        cleaned = "\n".join(content).strip()
        rebuilt.append(f"{section}\n{cleaned}")

    body = "\n\n".join(rebuilt)
    return Result(f"{title}\n\n{body}", warnings)


def split_pr(text):
    """검증된 PR 텍스트를 (제목, 본문)으로 나눈다."""
    lines = text.splitlines()
    return lines[0].strip(), "\n".join(lines[1:]).strip()
