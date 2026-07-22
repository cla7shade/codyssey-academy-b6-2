"""AI 기반 Git 커밋 & PR 자동 생성기.

사용법:
    python main.py commit    커밋 메시지 생성
    python main.py pr        PR 제목/본문 초안 생성

API Key는 AI_API_KEY 환경변수로 전달한다.
"""

import argparse
import sys

from gitgen import ai_client, git, prompts, render, sanitizer, validator

EXIT_OK = 0
EXIT_ERROR = 1

# PR 의 기준 브랜치. --base 로 바꿀 수 있다.
DEFAULT_BASE = "main"


def build_parser():
    parser = argparse.ArgumentParser(
        prog="python main.py",
        description="Git 변경 사항을 기반으로 커밋 메시지와 PR 초안을 생성합니다.",
    )

    # commit 과 pr 이 같은 옵션을 공유하도록 부모 파서에 모아 둔다.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--model",
        default=ai_client.DEFAULT_MODEL,
        help=f"사용할 모델 ID (기본: {ai_client.DEFAULT_MODEL})",
    )
    common.add_argument(
        "--temperature",
        type=float,
        default=ai_client.DEFAULT_TEMPERATURE,
        help="샘플링 무작위성 0.0~2.0. 낮을수록 결정적 "
             f"(기본: {ai_client.DEFAULT_TEMPERATURE})",
    )
    common.add_argument(
        "--max-tokens",
        type=int,
        default=ai_client.DEFAULT_MAX_TOKENS,
        dest="max_tokens",
        help=f"최대 출력 토큰 (기본: {ai_client.DEFAULT_MAX_TOKENS})",
    )
    common.add_argument(
        "--thinking-budget",
        type=int,
        default=None,
        dest="thinking_budget",
        help="추론에 쓸 토큰 수. 0이면 추론을 끄고, 음수면 이 설정을 보내지 않는다 "
             "(기본: 모델에 따라 자동)",
    )
    common.add_argument(
        "--safe-mode",
        action="store_true",
        default=True,
        dest="safe_mode",
        help="민감정보 마스킹 + diff 크기 제한 (기본: 켜짐)",
    )
    common.add_argument(
        "--no-safe-mode",
        action="store_false",
        dest="safe_mode",
        help="safe-mode 를 끄고 diff 원문을 전송 (권장하지 않음)",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("commit", parents=[common], help="커밋 메시지를 생성합니다.")
    pr = subparsers.add_parser(
        "pr", parents=[common], help="PR 제목/본문 초안을 생성합니다."
    )
    pr.add_argument(
        "--base",
        default=DEFAULT_BASE,
        help=f"PR 을 보낼 기준 브랜치 (기본: {DEFAULT_BASE})",
    )

    return parser


def _pr_diff(args):
    """PR 용 diff 를 고른다. (diff 텍스트, 무엇을 봤는지)

    PR 은 커밋이 끝난 브랜치 전체를 설명하는 문서다. 그 시점의 작업
    트리는 비어 있는 게 정상이므로 인덱스가 아니라 base 브랜치와의
    차이를 봐야 한다.

    base 위에 그대로 서 있거나 base 를 찾을 수 없으면 비교 대상이
    없으므로, 아직 커밋하지 않은 스테이징 변경으로 넘어간다.
    """
    branch = git.get_current_branch()

    if branch == args.base:
        return git.get_diff(), "스테이징된 변경"

    if not git.ref_exists(args.base):
        render.warn(
            f"기준 브랜치 '{args.base}' 를 찾을 수 없습니다. "
            "--base 로 지정하거나, 스테이징된 변경으로 생성합니다."
        )
        return git.get_diff(), "스테이징된 변경"

    return git.get_branch_diff(args.base), f"{args.base}...{branch}"


def collect_changes(args):
    """Git 변경 사항을 수집한다. 변경이 없으면 None 을 돌려준다."""
    if not git.is_git_repo():
        render.error(
            "Git 저장소가 아닙니다. Git이 초기화된 프로젝트 루트에서 실행하세요."
        )
        sys.exit(EXIT_ERROR)

    status = git.get_status()
    render.info(f"Git status 수집 완료: {len(status)}개 파일 변경 감지")

    if args.command == "pr":
        diff, source = _pr_diff(args)
    else:
        diff, source = git.get_diff(), "스테이징된 변경"

    if not diff.strip():
        render.info(f"{source}에서 얻은 diff 가 비었습니다. 생성하지 않고 종료합니다.")
        if source == "스테이징된 변경" and status:
            render.info("`git add <파일>` 로 커밋할 변경을 올린 뒤 다시 실행하세요.")
        return None

    render.info(f"Git diff 수집 완료: {len(diff.splitlines())}줄 ({source})")

    report = sanitizer.sanitize(diff, enabled=args.safe_mode)
    if args.safe_mode:
        render.info(f"safe-mode 적용: {report.summary()}")
    else:
        render.warn("safe-mode 가 꺼져 있습니다. diff 원문이 그대로 전송됩니다.")

    return git.format_status(status), report.text


def run_commit(args, status_text, diff_text):
    prompt = prompts.build_commit_prompt(status_text, diff_text)

    render.info("AI API 요청 중...")
    raw = ai_client.generate(
        prompt,
        model=args.model,
        temperature=args.temperature,
        max_tokens=args.max_tokens,
        thinking_budget=args.thinking_budget,
    )

    result = validator.validate_commit(raw)
    render.done("커밋 메시지 생성 완료")
    for warning in result.warnings:
        render.warn(warning)

    render.block("Commit Message", result.text)


def run_pr(args, status_text, diff_text):
    branch = git.get_current_branch()
    render.info(f"현재 브랜치: {branch}")

    prompt = prompts.build_pr_prompt(status_text, diff_text, branch)

    render.info("AI API 요청 중...")
    raw = ai_client.generate(
        prompt,
        model=args.model,
        temperature=args.temperature,
        max_tokens=args.max_tokens,
        thinking_budget=args.thinking_budget,
    )

    result = validator.validate_pr(raw)
    render.done("PR 초안 생성 완료")
    for warning in result.warnings:
        render.warn(warning)

    title, body = validator.split_pr(result.text)
    render.block("PR Title", title)
    render.block("PR Body", body)


def main():
    args = build_parser().parse_args()

    try:
        changes = collect_changes(args)
        if changes is None:
            return EXIT_OK

        status_text, diff_text = changes

        if args.command == "commit":
            run_commit(args, status_text, diff_text)
        else:
            run_pr(args, status_text, diff_text)

    except git.GitError as exc:
        render.error(str(exc))
        return EXIT_ERROR
    except ai_client.AIClientError as exc:
        render.error(str(exc))
        return EXIT_ERROR
    except KeyboardInterrupt:
        render.error("사용자가 중단했습니다.")
        return EXIT_ERROR
    finally:
        # 비용 파악을 위해 호출 횟수를 항상 남긴다.
        count = ai_client.get_call_count()
        if count:
            render.info(f"AI API 호출 횟수: {count}회")

    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
