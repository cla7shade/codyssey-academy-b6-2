"""Gemini API를 REST 방식으로 호출한다.

SDK 대신 requests 로 직접 HTTP 요청을 구성해
요청 생성 -> 응답 처리 -> 예외 대응의 전체 흐름을 드러낸다.
"""

import os

import requests

API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
# 커밋 메시지/PR 초안은 긴 추론이 필요한 작업이 아니다.
# flash-lite 는 flash 대비 입력 1/5, 출력 약 1/4 가격이라 기본값으로 쓴다.
DEFAULT_MODEL = "gemini-3.5-flash-lite"
DEFAULT_TEMPERATURE = 0.3
DEFAULT_MAX_TOKENS = 1024
TIMEOUT_SECONDS = 30

# thinkingConfig 를 받아들이는 모델.
# gemini-3.5-flash 는 받아들이고 gemini-3.5-flash-lite 는 거부한다.
# (2026-07-22, generateContent 에 직접 요청해 확인)
THINKING_CAPABLE_MODELS = frozenset({"gemini-3.5-flash"})


def default_thinking_budget(model):
    """모델에 맞는 thinkingBudget 기본값을 고른다.

    지원하는 모델에는 0(추론 끔)을 준다. 추론 토큰이 maxOutputTokens
    예산을 같이 쓰기 때문에, 켜 둔 채로는 커밋 메시지가 잘려 나온다.

    목록에 없으면 -1 이다. -1 은 이 필드를 아예 보내지 않는다는 뜻이라
    지원 여부를 모르는 모델에서도 400 이 나지 않는다.
    """
    return 0 if model in THINKING_CAPABLE_MODELS else -1

ENV_KEY_NAME = "AI_API_KEY"

# 1회 실행당 호출 횟수를 사용자에게 보여주기 위한 카운터.
_call_count = 0


class AIClientError(Exception):
    """API 호출 실패. message 는 그대로 사용자에게 보여줄 수 있는 형태다."""


def get_call_count():
    return _call_count


def load_api_key():
    """환경변수에서 API Key를 읽는다. 코드에 하드코딩하지 않는다."""
    key = os.environ.get(ENV_KEY_NAME, "").strip()
    if not key:
        raise AIClientError(
            f"{ENV_KEY_NAME} 환경변수가 설정되지 않았습니다.\n"
            f'       예) export {ENV_KEY_NAME}="YOUR_KEY"'
        )
    return key


def _build_payload(prompt, temperature, max_tokens, thinking_budget):
    """CLI 옵션을 Gemini 요청 바디로 옮긴다.

    temperature 와 maxOutputTokens 가 CLI 옵션과 1:1로 대응한다.
    """
    config = {
        "temperature": temperature,
        "maxOutputTokens": max_tokens,
    }
    # 음수는 "thinkingConfig 를 아예 보내지 않는다"는 뜻이다.
    # flash-lite 처럼 이 필드를 거부하는 모델이 있어 빠져나갈 길이 필요하다.
    if thinking_budget is not None and thinking_budget >= 0:
        config["thinkingConfig"] = {"thinkingBudget": thinking_budget}

    return {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": config,
    }


def _extract_text(data):
    """응답 JSON에서 생성된 텍스트를 꺼낸다."""
    candidates = data.get("candidates") or []
    if not candidates:
        # 프롬프트 자체가 차단된 경우 candidates 없이 promptFeedback 만 온다.
        feedback = data.get("promptFeedback", {})
        reason = feedback.get("blockReason")
        if reason:
            raise AIClientError(f"프롬프트가 안전 필터에 의해 차단되었습니다: {reason}")
        raise AIClientError("응답에 생성 결과가 없습니다.")

    candidate = candidates[0]
    parts = candidate.get("content", {}).get("parts") or []
    # 추론 과정(thought)은 결과물이 아니므로 제외한다.
    text = "".join(
        part.get("text", "") for part in parts if not part.get("thought")
    ).strip()

    finish = candidate.get("finishReason", "UNKNOWN")

    if not text:
        if finish == "MAX_TOKENS":
            raise AIClientError(
                "출력 토큰 한도에 걸려 결과가 비었습니다. "
                "--max-tokens 값을 늘리거나 --thinking-budget 0 으로 실행하세요."
            )
        raise AIClientError(f"응답 형식이 올바르지 않습니다. (finishReason={finish})")

    # 텍스트가 있어도 한도에 걸렸다면 중간에 잘린 결과다.
    # 조용히 넘기면 사용자가 불완전한 초안을 그대로 쓰게 된다.
    if finish == "MAX_TOKENS":
        raise AIClientError(
            "출력 토큰 한도에 걸려 결과가 중간에 잘렸습니다. "
            "--max-tokens 값을 늘려서 다시 실행하세요."
        )

    return text


def _error_message(response):
    """오류 응답에서 원인 문구를 뽑아낸다."""
    try:
        payload = response.json()
    except ValueError:
        return response.text.strip()[:200] or "(본문 없음)"
    return payload.get("error", {}).get("message", "").strip() or "(상세 메시지 없음)"


def generate(prompt, model=DEFAULT_MODEL, temperature=DEFAULT_TEMPERATURE,
             max_tokens=DEFAULT_MAX_TOKENS, thinking_budget=None):
    """프롬프트를 보내고 생성된 텍스트를 돌려준다.

    thinking_budget 이 None 이면 모델에 맞는 기본값을 골라 쓴다.
    실패 시에는 원인을 담은 AIClientError 를 던진다.
    """
    global _call_count

    if thinking_budget is None:
        thinking_budget = default_thinking_budget(model)

    api_key = load_api_key()
    url = f"{API_BASE}/{model}:generateContent"
    headers = {
        "x-goog-api-key": api_key,
        "Content-Type": "application/json",
    }

    try:
        response = requests.post(
            url,
            headers=headers,
            json=_build_payload(prompt, temperature, max_tokens, thinking_budget),
            timeout=TIMEOUT_SECONDS,
        )
        # 서버까지 요청이 도달한 경우만 호출로 센다.
        # 연결 자체가 실패하면 과금되지 않으므로 카운트하지 않는다.
        _call_count += 1
    except requests.exceptions.Timeout:
        raise AIClientError(f"네트워크 오류: 응답이 {TIMEOUT_SECONDS}초 안에 오지 않았습니다.")
    except requests.exceptions.ConnectionError as exc:
        raise AIClientError(f"네트워크 오류: 서버에 연결할 수 없습니다. ({exc.__class__.__name__})")
    except requests.exceptions.RequestException as exc:
        raise AIClientError(f"요청 실패: {exc}")

    status = response.status_code
    detail = _error_message(response) if status >= 400 else ""

    # Gemini 는 잘못된 키에 401 이 아니라 400 + "API key not valid" 를 돌려준다.
    # 상태 코드만 보면 일반 요청 오류로 오해하므로 본문까지 확인한다.
    if status in (401, 403) or (status == 400 and "api key" in detail.lower()):
        raise AIClientError(f"인증 실패: API Key를 확인하세요. ({detail})")
    if status == 429:
        raise AIClientError(f"요청 한도 초과: 잠시 후 다시 시도하세요. ({detail})")
    if status == 404:
        raise AIClientError(
            f"모델을 찾을 수 없습니다: {model} — --model 옵션을 확인하세요. ({detail})"
        )
    if status >= 400:
        hint = ""
        # thinkingConfig 를 지원하지 않는 모델이 있다. 원인을 짚어 주지 않으면
        # 사용자는 "invalid argument" 만 보고 무엇을 고쳐야 할지 알 수 없다.
        if status == 400 and thinking_budget is not None and thinking_budget >= 0:
            hint = (
                f"\n       {model} 이(가) thinkingBudget 을 지원하지 않을 수 있습니다. "
                "--thinking-budget -1 로 다시 실행해 보세요."
            )
        raise AIClientError(f"API 호출 실패 (HTTP {status}): {detail}{hint}")

    try:
        data = response.json()
    except ValueError:
        raise AIClientError("응답을 JSON으로 해석할 수 없습니다.")

    return _extract_text(data)
