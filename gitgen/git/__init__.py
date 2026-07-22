"""Git 연동 패키지.

  errors.py   - GitError 예외
  runner.py   - subprocess 로 git 명령을 실행
  commands.py - status / diff / branch 수집

바깥에서는 `from gitgen import git` 후 `git.get_status()` 처럼 쓴다.
"""

from .commands import (
    format_status,
    get_branch_diff,
    get_current_branch,
    get_diff,
    get_status,
    is_git_repo,
    ref_exists,
)
from .errors import GitError

__all__ = [
    "GitError",
    "format_status",
    "get_branch_diff",
    "get_current_branch",
    "get_diff",
    "get_status",
    "is_git_repo",
    "ref_exists",
]
