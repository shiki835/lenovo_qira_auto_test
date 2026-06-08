"""Multi-tier judgment engine for chat responses.

L1: Rule-based checks (error keywords, timeout detection from error field).
L2: Qwen3-VL via vLLM — sends screenshot + expected answer to the vision model.
    Model looks at the screenshot directly and returns PASS / FAIL / UNCERTAIN.
"""

import json
import base64
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
    screenshot_path: str
    verdict: str  # PASS, FAIL, UNCERTAIN
    l1_pass: bool
    l2_verdict: str
    l2_reason: str
    l2_raw: str  # raw model response
    error: str


def judge(results: RunResults, config: Config) -> list[JudgeResult]:
    """Run all judgment tiers on a set of results."""
    output = []
    for idx, entry in sorted(results.results.items()):
        l1_ok, l1_reason = _run_l1(entry, config)
        l2_verdict = ""
        l2_reason = ""

        if config.judge.llm_enabled:
            screenshot_path = entry.screenshot_path or ""
            if screenshot_path and Path(screenshot_path).exists():
                l2_verdict, l2_reason, l2_raw = _run_l2(entry, config)
            else:
                l2_reason = "L2 skipped: screenshot not found"
                l2_raw = ""
        else:
            l2_reason = "L2 skipped: llm_enabled=false"
            l2_raw = ""

        verdict = _combine(l1_ok, l2_verdict)
        output.append(JudgeResult(
            index=idx,
            question=entry.question,
            expected=entry.expected,
            screenshot_path=entry.screenshot_path,
            verdict=verdict,
            l1_pass=l1_ok,
            l2_verdict=l2_verdict,
            l2_reason=l2_reason,
            l2_raw=l2_raw,
            error=entry.error,
        ))
    return output


def judge_version(version: str, config: Config) -> list[JudgeResult]:
    """Load a version's results and judge them."""
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
    """Run level-1 rule checks on the error field and response text."""
    if entry.error == "TIMEOUT":
        return False, "L1: timeout"
    if entry.error == "SEND_BUTTON_NOT_FOUND":
        return False, "L1: send button not found"

    response = entry.response
    if response.strip():
        for kw in config.judge.error_keywords:
            if kw in response:
                return False, f"L1: contains error keyword: {kw}"
        if len(response.strip()) < 2:
            return False, "L1: response too short"

    # If response text is empty but there's a screenshot, L1 passes
    # (the vision model in L2 will do the actual evaluation)
    if not response.strip() and entry.screenshot_path:
        return True, "L1: OK (no text, screenshot available for L2)"

    return True, "L1: OK"


# ------------------------------------------------------------------
# L2: Qwen3-VL via vLLM (vision model)
# ------------------------------------------------------------------

_L2_PROMPT = """You are a test evaluator. Look at this screenshot of a chatbot conversation. The user asked a question, and the chatbot replied. Judge whether the chatbot's response matches the expected answer.

Question: {question}
Expected answer: {expected}

Rules:
- The response does NOT need to match word-for-word.
- If the response covers the key points in the expected answer, reply PASS.
- If the response contradicts the expected answer or misses critical information, reply FAIL.
- If you are genuinely uncertain (e.g., the screenshot is unclear, the question is ambiguous), reply UNCERTAIN.
- If the screenshot shows an error message, network error, or blank response, reply FAIL.

Reply with exactly one word on the first line: PASS, FAIL, or UNCERTAIN.
On the second line, give a one-sentence reason in Chinese."""


def _encode_image(image_path: str) -> str:
    """Read image file and encode as base64 data URL."""
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def _run_l2(entry: ResultEntry, config: Config) -> tuple[str, str, str]:
    """Run Qwen3-VL evaluation via Ollama OpenAI-compatible API.

    Returns (verdict, reason, raw_response).
    """
    try:
        from openai import OpenAI
    except ImportError:
        return "UNCERTAIN", "L2 skipped: openai SDK not installed", ""

    screenshot_path = entry.screenshot_path
    if not screenshot_path or not Path(screenshot_path).exists():
        return "UNCERTAIN", "L2 skipped: screenshot file not found", ""

    try:
        b64 = _encode_image(screenshot_path)
    except Exception as e:
        return "UNCERTAIN", f"L2 skipped: cannot read screenshot ({e})", ""

    prompt = _L2_PROMPT.format(
        question=entry.question,
        expected=entry.expected or "(none provided)",
    )

    try:
        client = OpenAI(
            base_url=config.judge.ollama_base_url,
            api_key="ollama",
        )
        response = client.chat.completions.create(
            model=config.judge.ollama_model,
            max_tokens=config.judge.ollama_max_tokens,
            temperature=config.judge.ollama_temperature,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {
                        "url": f"data:image/png;base64,{b64}"
                    }},
                ],
            }],
        )
        raw_text = response.choices[0].message.content or ""
        text = raw_text.strip()
        lines = text.split("\n", 1)
        verdict = lines[0].strip().upper()
        reason = lines[1].strip() if len(lines) > 1 else ""

        if verdict not in ("PASS", "FAIL", "UNCERTAIN"):
            verdict = "UNCERTAIN"
            reason = f"Unexpected response: {text[:80]}"

        return verdict, reason, raw_text
    except Exception as e:
        logger.error(f"L2 Ollama call failed: {e}")
        return "UNCERTAIN", f"L2 API error: {e}", ""


# ------------------------------------------------------------------
# Combine L1 + L2
# ------------------------------------------------------------------

def save_judge_results(results: list[JudgeResult], version: str):
    """Save judge results to Excel in the results directory."""
    import openpyxl

    results_dir = Path(__file__).parent.parent / "results" / version
    output_path = results_dir / "judge_results.xlsx"

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Judge Results"
    ws.append(["序号", "问题", "期望答案", "判定结果", "模型原始回复", "判定原因", "截图路径"])

    for r in results:
        ws.append([
            r.index, r.question, r.expected,
            r.verdict, r.l2_raw, r.l2_reason, r.screenshot_path,
        ])

    # Adjust column widths
    ws.column_dimensions["A"].width = 6
    ws.column_dimensions["B"].width = 30
    ws.column_dimensions["C"].width = 30
    ws.column_dimensions["D"].width = 12
    ws.column_dimensions["E"].width = 40
    ws.column_dimensions["F"].width = 30
    ws.column_dimensions["G"].width = 50

    # Bold for FAIL rows
    from openpyxl.styles import Font
    for row in ws.iter_rows(min_row=2):
        if row[3].value == "FAIL":
            for cell in row:
                cell.font = Font(bold=True, color="FF0000")

    wb.save(str(output_path))
    wb.close()
    print(f"Judge results saved to: {output_path}")
    return str(output_path)


def _combine(l1_ok: bool, l2_verdict: str) -> str:
    if not l1_ok:
        return "FAIL"
    if l2_verdict:
        return l2_verdict
    return "UNCERTAIN"
