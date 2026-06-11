"""Multi-tier judgment engine for chat responses.

L1: Rule-based checks (non-empty, no error keywords, length range).
L2: Claude API evaluation (PASS / FAIL / UNCERTAIN).
"""

import json
import logging
from pathlib import Path
from dataclasses import dataclass

from .config import Config
from .executor import RunResults, ResultEntry

logger = logging.getLogger(__name__)


@dataclass
class JudgeResult:
    index: int
    question: str
    expected: str
    response: str
    verdict: str  # PASS, FAIL, UNCERTAIN
    l1_pass: bool
    l2_verdict: str  # "" if L2 skipped
    l2_reason: str
    error: str


def judge(results: RunResults, config: Config) -> list[JudgeResult]:
    """Run all judgment tiers on a set of results."""
    output = []
    for idx, entry in sorted(results.results.items()):
        l1_ok, l1_reason = _run_l1(entry, config)
        l2_verdict = ""
        l2_reason = ""

        if config.judge.llm_enabled and l1_ok:
            # Only run L2 if L1 passed (obvious failures skip the LLM cost)
            l2_verdict, l2_reason = _run_l2(entry)

        verdict = _combine(l1_ok, l2_verdict)
        output.append(JudgeResult(
            index=idx,
            question=entry.question,
            expected=entry.expected,
            response=entry.response,
            verdict=verdict,
            l1_pass=l1_ok,
            l2_verdict=l2_verdict,
            l2_reason=l2_reason,
            error=entry.error,
        ))
    return output


def judge_version(version: str, config: Config) -> list[JudgeResult]:
    """Convenience: load a version's results and judge them."""
    results_path = (
        Path(__file__).parent.parent / "results" / version / "raw_responses.json"
    )
    if not results_path.exists():
        raise FileNotFoundError(f"No results found for version: {version}")

    with open(results_path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    results = RunResults(
        version=raw["version"],
        source_file=raw["source_file"],
        started_at=raw["started_at"],
        completed_at=raw.get("completed_at", ""),
        total=raw["total"],
        completed=raw["completed"],
    )
    for k, v in raw.get("results", {}).items():
        results.results[int(k)] = ResultEntry(**v)

    return judge(results, config)


# ------------------------------------------------------------------
# L1: Rule-based checks
# ------------------------------------------------------------------

def _run_l1(entry: ResultEntry, config: Config) -> tuple[bool, str]:
    """Run level-1 rule checks. Returns (pass, reason)."""
    response = entry.response

    # 1. Non-empty
    if not response.strip():
        return False, "L1: empty response"

    # 2. No error keywords
    for kw in config.judge.error_keywords:
        if kw in response:
            return False, f"L1: contains error keyword: {kw}"

    # 3. Reasonable length (at least 2 chars, actual content)
    if len(response.strip()) < 2:
        return False, "L1: response too short"

    return True, "L1: OK"


# ------------------------------------------------------------------
# L2: Claude API evaluation
# ------------------------------------------------------------------

_L2_PROMPT = """You are a test evaluator. Judge whether the chatbot's ACTUAL answer matches the EXPECTED answer.

Question: {question}
Expected answer: {expected}
Actual answer: {actual}

Rules:
- The actual answer does NOT need to match word-for-word.
- If the actual answer covers the key points in the expected answer, it's a PASS.
- If the actual answer contradicts the expected answer or misses critical information, it's a FAIL.
- If you are genuinely uncertain (e.g., ambiguous question, borderline answer), it's UNCERTAIN.

Reply with exactly one word on the first line: PASS, FAIL, or UNCERTAIN.
On the second line, give a one-sentence reason in Chinese."""


def _run_l2(entry: ResultEntry) -> tuple[str, str]:
    """Run Claude API evaluation. Returns (verdict, reason)."""
    try:
        import anthropic
    except ImportError:
        return "UNCERTAIN", "L2 skipped: anthropic SDK not installed"

    import os
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return "UNCERTAIN", "L2 skipped: ANTHROPIC_API_KEY not set"

    prompt = _L2_PROMPT.format(
        question=entry.question,
        expected=entry.expected or "(none provided)",
        actual=entry.response,
    )

    try:
        client = anthropic.Anthropic(api_key=api_key)
        msg = client.messages.create(
            model=os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6"),
            max_tokens=100,
            temperature=0,
            messages=[{"role": "user", "content": prompt}],
        )
        text = msg.content[0].text.strip()
        lines = text.split("\n", 1)
        verdict = lines[0].strip().upper()
        reason = lines[1].strip() if len(lines) > 1 else ""

        if verdict not in ("PASS", "FAIL", "UNCERTAIN"):
            verdict = "UNCERTAIN"
            reason = f"Unexpected response: {text[:80]}"

        return verdict, reason
    except Exception as e:
        logger.error(f"L2 Claude call failed: {e}")
        return "UNCERTAIN", f"L2 API error: {e}"


# ------------------------------------------------------------------
# Combine L1 + L2
# ------------------------------------------------------------------

def _combine(l1_ok: bool, l2_verdict: str) -> str:
    if not l1_ok:
        return "FAIL"
    if l2_verdict:
        return l2_verdict
    return "UNCERTAIN"
