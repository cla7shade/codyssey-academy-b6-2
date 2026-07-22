"""Git 변경 사항을 프로그램 입력으로 수집한다.

수집 범위는 과제 제약사항에 따라 git status / git diff 로 제한한다.
git push 나 GitHub PR 생성 등 원격 저장소 반영 기능은 구현하지 않는다.
"""

from .errors import GitError
from .runner import run


def is_git_repo():
    """현재 디렉토리가 Git 작업 트리 안인지 확인한다."""
    try:
        return run(["rev-parse", "--is-inside-work-tree"]).strip() == "true"
    except GitError:
        return False


def get_status():
    """변경된 파일 목록을 [(상태코드, 경로), ...] 형태로 돌려준다.

    --porcelain 은 사람이 읽는 형식과 달리 출력이 고정되어 있어
    파싱이 안전하다. 각 줄은 'XY 파일경로' 형태다.
    """
    files = []
    for line in run(["status", "--porcelain"]).splitlines():
        if not line.strip():
            continue
        # 상태 코드는 항상 앞 2글자, 그 뒤 한 칸을 띄고 경로가 온다.
        # ' M file' 처럼 앞자리가 공백일 수 있어 split() 으로 자르면 안 된다.
        state, path = line[:2], line[3:]
        files.append((state, path.strip()))
    return files


def get_diff():
    """커밋될 변경 내용(diff 텍스트)을 돌려준다.

    실제로 커밋되는 것은 인덱스에 올라간 내용이므로 `--staged` 로 비교한다.
    커밋 메시지는 커밋될 내용을 설명해야 하고, 아직 스테이징하지 않은
    수정본은 이번 커밋에 들어가지 않는다.
    """
    return run(["diff", "--staged"])


def collect_diff():
    """커밋 대상 diff 를 골라 (diff 텍스트, 출처)로 돌려준다.

    staged 변경이 있으면 그것이 실제로 커밋될 내용이므로 우선한다.
    `git diff` 는 워킹트리의 수정본만 보여줘서 새로 add 한 파일을
    놓치는데, 사용자는 보통 add 를 마친 뒤에 커밋 메시지를 원한다.

    staged 가 비어 있으면 아직 add 전이라는 뜻이므로
    워킹트리 수정본으로 넘어간다.
    """
    staged = get_diff(staged=True)
    if staged.strip():
        return staged, "staged"
    return get_diff(), "worktree"


def get_branch_diff(base):
    """base 브랜치와 갈라진 지점부터 현재까지의 diff 를 돌려준다.

    PR 은 커밋이 끝난 브랜치 전체를 설명하는 것이라 인덱스가 아니라
    base 와의 차이를 봐야 한다. 세 점(...)은 갈라진 지점을 기준으로
    비교하므로, base 에 새 커밋이 쌓여도 그 변경이 섞이지 않는다.
    """
    return run(["diff", f"{base}...HEAD"])


def ref_exists(ref):
    """브랜치나 커밋이 실제로 있는지 확인한다."""
    try:
        run(["rev-parse", "--verify", "--quiet", ref])
        return True
    except GitError:
        return False


def get_current_branch():
    """현재 브랜치명을 돌려준다. 커밋이 없는 저장소도 처리한다."""
    try:
        return run(["rev-parse", "--abbrev-ref", "HEAD"]).strip()
    except GitError:
        # 아직 커밋이 하나도 없으면 HEAD를 해석할 수 없다.
        return run(["symbolic-ref", "--short", "HEAD"]).strip()


def format_status(files):
    """상태 목록을 프롬프트에 넣기 좋은 텍스트로 만든다."""
    if not files:
        return "(변경된 파일 없음)"
    return "\n".join(f"{state}\t{path}" for state, path in files)
