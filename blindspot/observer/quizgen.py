"""Quiz authoring helpers: pick a quiz target, write a prompt for any chat model,
and turn the model's pasted reply into questions the review store will accept.

Nothing here calls a model. The answer key comes from whoever wrote the reply and
is only shape-checked, so the interface labels it unproven."""
from __future__ import annotations

import json
import re

MIN_LINES = 10
MAX_LINES = 300
MAX_BYTES = 16 * 1024
KNOWN_NAMES = {"True", "False", "None", "self", "cls", "this", "null", "undefined"}


class QuizError(ValueError):
    """A problem with the quiz request or reply that is safe to show the user."""


def choose_range(text: str, item: dict) -> tuple[int, int, str]:
    """Inclusive line range for a quiz on one guide unit, within the review limits."""
    lines = text.splitlines(keepends=True)
    total = len(lines)
    if total < MIN_LINES: raise QuizError("This file is shorter than 10 lines, which is the smallest quiz target.")
    start, end = max(1, item["start"]), min(total, item["end"])
    note = ""
    if end - start + 1 < MIN_LINES:  # grow a short unit with its neighbours
        end = min(total, start + MIN_LINES - 1)
        start = max(1, end - MIN_LINES + 1)
        note = "This unit is short, so the quiz includes nearby lines."
    def size(a, b): return len("".join(lines[a - 1:b]).encode())
    if end - start + 1 > MAX_LINES or size(start, end) > MAX_BYTES:
        anchor = item["unseen_ranges"][0][0] if item.get("unseen_ranges") else start
        start = min(max(start, anchor), end)
        start = max(item["start"], min(start, end - MIN_LINES + 1))
        end = min(total, start + MAX_LINES - 1, end)
        while end - start + 1 > MIN_LINES and size(start, end) > MAX_BYTES: end -= 1
        note = f"This unit is long, so the quiz covers lines {start}-{end}."
    if end - start + 1 < MIN_LINES or size(start, end) > MAX_BYTES:
        raise QuizError("This section cannot fit ten lines within the quiz size limit. Choose a smaller section.")
    return start, end, note


def question_count(start: int, end: int) -> int:
    return 4 if end - start + 1 >= 40 else 3


def build_prompt(path: str, start: int, end: int, code: str, unseen_ranges: list, count: int) -> str:
    numbered = "\n".join(f"{n:>5}| {line}" for n, line in enumerate(code.splitlines(), start))
    unseen = ", ".join(f"{a}" if a == b else f"{a}-{b}" for a, b in unseen_ranges) or "none"
    example = {"questions": [{
        "prompt": "What happens when the input list is empty?",
        "options": ["It returns None", "It raises ValueError", "It returns an empty list", "It loops forever"],
        "correct_index": 1,
        "explanation": "One or two sentences on why the correct option is right.",
        "rationale": {"path": path, "start_line": start, "end_line": min(end, start + 1), "reason": "Which lines show this."}}]}
    return f"""You are writing a short multiple-choice quiz that checks whether a developer understands code they have not read.

Write exactly {count} questions about the code below (file {path}, lines {start}-{end}). The reader can look at the code while answering, so ask about behavior and reasoning, not memorization.

Rules:
- Each question has exactly 4 options. Exactly one is correct. The wrong options must be plausible mistakes, not jokes.
- Prefer questions like: what happens in an edge case, what breaks if a line is removed or changed, why a check comes before another, what a call returns for a given input.
- Weight the questions toward lines {unseen}, which the reader has never had on screen, when those lines hold real logic.
- Do not use "all of the above" or "none of the above". Vary which option is correct.
- Every question must be answerable from the code shown. If something cannot be known from it, do not ask about it.
- correct_index is 0-based (0 is the first option).
- rationale.start_line and rationale.end_line are real file line numbers, inside {start}-{end}, covering the lines that decide the answer.

Output format:
- Return valid JSON inside one ```json code block, with no text outside it.
- Inside the code block, use JSON syntax only. Do not add Markdown escapes to brackets, underscores, or comparison operators.
- Use double quotes for JSON keys and strings. Escape any double quotes inside a string, or avoid quoting words inside it.
- Use integers for correct_index and line numbers. Do not use trailing commas.
- Check that the complete object parses as JSON before replying.

Use this shape, expanding the questions list to exactly {count} questions:
```json
{json.dumps(example, indent=2)}
```

Code:
{numbered}
"""


# ---- reply parsing --------------------------------------------------------

def extract_json(reply: str):
    reply = (reply or "").strip()
    if not reply: raise QuizError("Paste the model's reply first.")
    candidates = [reply]
    fenced = re.findall(r"```(?:json)?\s*(.*?)```", reply, flags=re.S | re.I)
    candidates += [f.strip() for f in fenced]
    for open_, close in (("{", "}"), ("[", "]")):
        a, b = reply.find(open_), reply.rfind(close)
        if 0 <= a < b: candidates.append(reply[a:b + 1])
    for candidate in candidates:
        try: return json.loads(candidate)
        except ValueError: continue
    raise QuizError("I could not find valid JSON in that reply. Ask the model to reply with only the JSON object.")


def _letter(value):
    return "ABCD".index(value.strip().upper()) if isinstance(value, str) and re.fullmatch(r"\s*[A-Da-d]\s*", value) else None


def _strip_labels(options):
    pattern = re.compile(r"^\s*\(?([A-Da-d])[\).:]\s+")
    found = [pattern.match(o) if isinstance(o, str) else None for o in options]
    if all(found) and [m.group(1).upper() for m in found] == list("ABCD"):
        return [pattern.sub("", o, count=1) for o in options]
    return options


def _int(value):
    return int(value) if isinstance(value, str) and re.fullmatch(r"\s*\d+\s*", value) else value


def normalize(reply, path: str, start: int, end: int) -> list[dict]:
    """Questions in the shape the review store expects, from a pasted reply."""
    data = extract_json(reply)
    items = data.get("questions") if isinstance(data, dict) else data
    if not isinstance(items, list) or not items: raise QuizError("The reply has no \"questions\" list.")
    questions = []
    for number, raw in enumerate(items, 1):
        if not isinstance(raw, dict): raise QuizError(f"Question {number} is not an object.")
        prompt = raw.get("prompt", raw.get("question"))
        options = raw.get("options", raw.get("choices"))
        if not isinstance(prompt, str) or not prompt.strip(): raise QuizError(f"Question {number} has no prompt.")
        if not isinstance(options, list) or len(options) != 4 or not all(isinstance(o, str) and o.strip() for o in options):
            raise QuizError(f"Question {number} needs exactly 4 text options.")
        options = _strip_labels(options)
        answer = _int(raw["correct_index"]) if "correct_index" in raw else None
        if answer is None:
            for key in ("answer", "correct_answer", "correct", "answer_index"):
                if key not in raw: continue
                value = raw[key]
                answer = _letter(value)
                if answer is None and isinstance(value, str):
                    answer = next((i for i, o in enumerate(options) if " ".join(o.split()) == " ".join(value.split())), None)
                if answer is None and key == "answer_index": answer = _int(value)
                break
        if type(answer) is not int or not 0 <= answer < 4:
            raise QuizError(f"Question {number} needs correct_index from 0 to 3.")
        rationale = raw.get("rationale") if isinstance(raw.get("rationale"), dict) else {}
        a, b = _int(rationale.get("start_line")), _int(rationale.get("end_line"))
        if type(a) is not int or type(b) is not int: raise QuizError(f"Question {number} needs rationale start_line and end_line.")
        if not start <= a <= b <= end:
            raise QuizError(f"Question {number} cites lines {a}-{b}, outside the quiz range {start}-{end}.")
        explanation = raw.get("explanation") or rationale.get("reason")
        reason = rationale.get("reason") or raw.get("explanation")
        if not isinstance(explanation, str) or not isinstance(reason, str):
            raise QuizError(f"Question {number} needs an explanation and a rationale reason.")
        questions.append({"prompt": prompt, "options": options, "correct_index": answer, "explanation": explanation,
                          "rationale": {"path": rationale.get("path") or path, "start_line": a, "end_line": b, "reason": reason}})
    return questions


def grounding_warnings(questions: list[dict], code: str) -> list[str]:
    """Flag explanations that name identifiers absent from the code; the key may be wrong."""
    warnings = []
    for number, q in enumerate(questions, 1):
        text = q["explanation"] + " " + q["rationale"]["reason"]
        missing = []
        for token in re.findall(r"`([A-Za-z_][\w.]*)`", text):
            head = token.split(".")[0]
            if head not in KNOWN_NAMES and head not in code and token not in missing: missing.append(token)
        if missing:
            warnings.append(f"Question {number} mentions {', '.join('`' + m + '`' for m in missing[:3])}, which does not appear in this code.")
    return warnings
