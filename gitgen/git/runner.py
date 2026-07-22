"""git 명령 실행을 담당한다.

subprocess 를 직접 다루는 곳은 이 파일 하나로 모은다.
commands.py 는 여기서 제공하는 run() 만 사용한다.
"""

import subprocess

from .errors import GitError


def run(args):
    """git 명령을 실행하고 표준 출력을 돌려준다.

    check=True 대신 returncode를 직접 검사해 stderr 내용을
    사람이 읽을 수 있는 메시지로 바꿔 전달한다.
    """
    try:
        result = subprocess.run(
            ["git"] + args,
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        raise GitError("git 명령을 찾을 수 없습니다. Git이 설치되어 있는지 확인하세요.")

    if result.returncode != 0:
        detail = result.stderr.strip() or f"exit code {result.returncode}"
        raise GitError(f"git {' '.join(args)} 실패: {detail}")

    return result.stdout
