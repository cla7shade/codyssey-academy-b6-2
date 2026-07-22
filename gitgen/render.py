"""터미널 출력 형식을 담당한다.

모든 로그는 [INFO] / [WARN] / [DONE] / [ERROR] 접두사를 붙여
사용자가 진행 상황과 최종 결과물을 구분할 수 있게 한다.
"""

import sys

SEPARATOR_WIDTH = 60


def info(message):
    # 파이프로 연결하면 stdout이 버퍼링되어 stderr(오류)와 순서가 뒤바뀐다.
    # 로그는 진행 상황을 보여주는 용도이므로 매번 flush 한다.
    print(f"[INFO] {message}", flush=True)


def warn(message):
    print(f"[WARN] {message}", flush=True)


def done(message):
    print(f"[DONE] {message}", flush=True)


def error(message):
    """오류는 stderr로 보내 정상 출력과 섞이지 않게 한다."""
    print(f"[ERROR] {message}", file=sys.stderr, flush=True)


def block(title, body):
    """구분선과 헤더로 구획을 나눠 결과물을 출력한다.

    사용자가 이 블록만 복사해서 커밋 메시지나 PR 본문으로 쓸 수 있도록
    앞뒤를 명확히 구분한다.
    """
    print()
    print(f"--- {title} ---")
    print(body.strip())
    print("-" * SEPARATOR_WIDTH)
