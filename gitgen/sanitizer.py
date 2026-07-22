"""safe-mode: diff를 AI API로 보내기 전에 위험 요소를 걷어낸다.

두 가지를 함께 적용한다.
  (A) 마스킹  - API 키, 토큰, 이메일 등 민감정보 패턴을 치환한다.
  (B) 크기 제한 - 파일 수와 줄 수를 잘라 전송량을 줄인다.

무료 티어로 보낸 입력은 모델 제공자의 제품 개선에 사용될 수 있으므로
safe-mode 는 기본으로 켜 둔다.
"""

import re

MASK = "***MASKED***"

MAX_FILES = 10
MAX_LINES = 200

# 순서가 중요하다. 값이 있는 key=value 형태를 먼저 지워야
# 뒤의 범용 토큰 패턴이 키 이름까지 삼키지 않는다.
PATTERNS = [
    # PASSWORD= / SECRET= / TOKEN= / API_KEY= 형태의 환경변수 라인
    (
        "환경변수 시크릿",
        re.compile(
            r"(?i)\b([A-Z0-9_]*(?:PASSWORD|SECRET|TOKEN|API_?KEY|CREDENTIAL)[A-Z0-9_]*)"
            r"(\s*[=:]\s*)"
            r"(\"[^\"]*\"|'[^']*'|[^\s\"']+)"
        ),
        r"\1\2" + MASK,
    ),
    # 제공자별 키 접두사: OpenAI(sk-), Google(AIza), GitHub(ghp_ 등), Slack(xox_)
    (
        "API 키",
        re.compile(r"\b(?:sk-[A-Za-z0-9_\-]{16,}|AIza[A-Za-z0-9_\-]{20,}"
                   r"|gh[pousr]_[A-Za-z0-9]{16,}|xox[baprs]-[A-Za-z0-9\-]{10,})"),
        MASK,
    ),
    # 이메일 주소
    (
        "이메일",
        re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"),
        MASK,
    ),
    # PEM 개인키 블록
    (
        "개인키",
        re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"),
        MASK,
    ),
    # 32자 이상 hex 문자열 (해시로 보이는 토큰)
    (
        "긴 토큰",
        re.compile(r"\b[0-9a-fA-F]{32,}\b"),
        MASK,
    ),
]


class SanitizeReport:
    """safe-mode 가 무엇을 했는지 사용자에게 알려주기 위한 결과 묶음."""

    def __init__(self, text, masked_count, dropped_files, dropped_lines):
        self.text = text
        self.masked_count = masked_count
        self.dropped_files = dropped_files
        self.dropped_lines = dropped_lines

    @property
    def changed(self):
        return bool(self.masked_count or self.dropped_files or self.dropped_lines)

    def summary(self):
        parts = []
        if self.masked_count:
            parts.append(f"{self.masked_count}개 항목 마스킹")
        if self.dropped_files:
            parts.append(f"{self.dropped_files}개 파일 제외")
        if self.dropped_lines:
            parts.append(f"{self.dropped_lines}줄 절삭")
        return ", ".join(parts) if parts else "변경 없음"


def mask_secrets(text):
    """민감정보 패턴을 치환하고 (치환된 텍스트, 치환 횟수)를 돌려준다."""
    total = 0
    for _label, pattern, replacement in PATTERNS:
        text, count = pattern.subn(replacement, text)
        total += count
    return text, total


def _split_by_file(diff_text):
    """diff 텍스트를 파일 단위 청크로 나눈다.

    'diff --git' 이 각 파일 블록의 시작이다.
    """
    if not diff_text.strip():
        return []

    chunks = []
    current = []
    for line in diff_text.splitlines(keepends=True):
        if line.startswith("diff --git ") and current:
            chunks.append("".join(current))
            current = [line]
        else:
            current.append(line)
    if current:
        chunks.append("".join(current))
    return chunks


def limit_diff(diff_text, max_files=MAX_FILES, max_lines=MAX_LINES):
    """파일 수와 줄 수를 제한한다.

    파일 경계를 지켜서 자르기 때문에 잘린 diff 도 여전히
    모델이 읽을 수 있는 형태를 유지한다.
    """
    chunks = _split_by_file(diff_text)
    total_files = len(chunks)
    total_lines = len(diff_text.splitlines())

    kept = []
    used_lines = 0
    for chunk in chunks[:max_files]:
        chunk_lines = chunk.splitlines()
        if used_lines + len(chunk_lines) > max_lines:
            remaining = max_lines - used_lines
            if remaining > 0:
                kept.append("\n".join(chunk_lines[:remaining]) + "\n")
                used_lines += remaining
            break
        kept.append(chunk)
        used_lines += len(chunk_lines)

    dropped_files = max(0, total_files - max_files)
    dropped_lines = max(0, total_lines - used_lines)

    text = "".join(kept)
    if dropped_files or dropped_lines:
        text += (
            f"\n... ({dropped_files}개 파일, {dropped_lines}줄이 safe-mode 로 생략됨)\n"
        )

    return text, dropped_files, dropped_lines


def sanitize(diff_text, enabled=True, max_files=MAX_FILES, max_lines=MAX_LINES):
    """safe-mode 전체 파이프라인. 꺼져 있으면 원문을 그대로 돌려준다."""
    if not enabled:
        return SanitizeReport(diff_text, 0, 0, 0)

    masked, masked_count = mask_secrets(diff_text)
    limited, dropped_files, dropped_lines = limit_diff(masked, max_files, max_lines)
    return SanitizeReport(limited, masked_count, dropped_files, dropped_lines)
