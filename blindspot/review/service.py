from __future__ import annotations

from datetime import datetime
import math
from pathlib import Path
import uuid

from ..scan.repo import RepoError, Repository
from . import ReviewError
from .store import ReviewStore, sequence
from .targets import binding, block, currentness, digest, validate_manifest

CONFIDENCE = ("solid", "shaky", "guessed")
PURPOSES = ("workflow-test", "understanding-review")
USEFULNESS = ("yes", "no", "unsure", "unreported")
FAMILIARITY = ("unfamiliar", "some", "familiar")


def text(value, field: str, limit: int = 4000) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ReviewError(f"{field} must be nonempty text of at most {limit} characters.")
    return value.strip()


def _normalized(value):
    if isinstance(value, str):
        return " ".join(value.split())
    if isinstance(value, list):
        return [_normalized(v) for v in value]
    if isinstance(value, dict):
        return {k: _normalized(v) for k, v in value.items()}
    return value


def validate_questions(value, manifest: dict) -> list[dict]:
    if not isinstance(value, list) or not 3 <= len(value) <= 5:
        raise ReviewError("A quiz must contain 3–5 questions.")
    questions = []
    for ordinal, q in enumerate(value, 1):
        if not isinstance(q, dict):
            raise ReviewError("Each question must be an object.")
        prompt = text(q.get("prompt"), "Question prompt")
        options = q.get("options")
        if not isinstance(options, list) or len(options) != 4:
            raise ReviewError("Each question must have exactly four options.")
        options = [text(o, "Option", 2000) for o in options]
        if len({" ".join(o.split()) for o in options}) != 4:
            raise ReviewError("Question options must be distinct.")
        answer = q.get("correct_index")
        if type(answer) is not int or not 0 <= answer < 4:
            raise ReviewError("correct_index must be an integer from 0 to 3.")
        rationale = q.get("rationale")
        if not isinstance(rationale, dict):
            raise ReviewError("Each question requires a source rationale with path, line range, and reason.")
        a, b = rationale.get("start_line"), rationale.get("end_line")
        if type(a) is not int or type(b) is not int or not any(
            c["path"] == rationale.get("path") and c["start_line"] <= a <= b <= c["end_line"]
            for c in [manifest["target"], *manifest["context"]]):
            raise ReviewError("Rationale must cite a range inside the exported target/context.")
        questions.append({"id": f"q{ordinal}", "prompt": prompt, "options": options,
            "correct_index": answer, "explanation": text(q.get("explanation"), "Explanation"),
            "rationale": {"path": rationale["path"], "start_line": a, "end_line": b,
                          "reason": text(rationale.get("reason"), "Source rationale")}})
    if len({" ".join(q["prompt"].split()) for q in questions}) != len(questions):
        raise ReviewError("Question prompts must be distinct.")
    return questions


def _set(data: dict, set_id: str) -> dict:
    if set_id not in data["sets"]:
        raise ReviewError("Unknown quiz set ID.")
    return data["sets"][set_id]


def _attempt(data: dict, attempt_id: str) -> tuple[dict, dict]:
    if attempt_id not in data["attempts"]:
        raise ReviewError("Unknown attempt ID.")
    attempt = data["attempts"][attempt_id]
    return attempt, _set(data, attempt["set_id"])


def _require_current(quiz: dict) -> Repository:
    if quiz["status"] != "validated":
        raise ReviewError("This set is rejected and cannot be served.")
    repo = Repository(Path(quiz["manifest"]["checkout"]))
    status = currentness(repo, quiz["manifest"])
    if status != "current":
        raise ReviewError(f"Quiz target is {status}; export/import a fresh set.")
    return repo


def _grades(quiz: dict, attempt: dict) -> list[dict]:
    return [{"question_id": q["id"], "chosen_index": attempt["answers"][q["id"]]["chosen_index"],
             "confidence": attempt["answers"][q["id"]]["confidence"],
             "correct": attempt["answers"][q["id"]]["chosen_index"] == q["correct_index"]}
            for q in quiz["questions"]]


class ReviewService:
    def __init__(self, directory: Path, read_only: bool = False):
        self.store = ReviewStore(directory, read_only)

    def _guard_set(self, quiz: dict) -> None:
        if quiz.get("manifest"):
            self.store.guard(Path(quiz["manifest"]["checkout"]))

    def import_quiz(self, value: object, now: datetime) -> dict:
        # Validate before publishing: invalid sets retain a reason but no raw input.
        manifest = None
        error = None
        raw_manifest = value.get("manifest") if isinstance(value, dict) else None
        if isinstance(raw_manifest, dict) and isinstance(raw_manifest.get("checkout"), str):
            self.store.guard(Path(raw_manifest["checkout"]))
        try:
            if not isinstance(value, dict) or type(value.get("schema_version")) is not int or value["schema_version"] != 1:
                raise ReviewError("Quiz requires schema_version 1, manifest, generator, and questions.")
            repo, manifest = validate_manifest(value.get("manifest"))
            self.store.guard(repo.root)
            questions = validate_questions(value.get("questions"), manifest)
            generator = text(value.get("generator"), "Generator", 200)
            fingerprint = digest({"binding": binding(manifest),
                "questions": [_normalized({k: v for k, v in q.items() if k != "id"}) for q in questions]})
        except (ReviewError, RepoError) as exc:
            error = str(exc)
        if manifest is not None:
            self.store.guard(Path(manifest["checkout"]))
        with self.store.transaction() as data:
            if error is not None:
                set_id = uuid.uuid4().hex
                data["sets"][set_id] = {"id": set_id, "status": "rejected", "reason": error,
                    "validation_version": 1,
                    "imported_at": now.isoformat(), "import_sequence": sequence(data),
                    "manifest": manifest}
                return {"set_id": set_id, "status": "rejected", "reason": error}
            for existing in data["sets"].values():
                if existing.get("fingerprint") == fingerprint:
                    return {"set_id": existing["id"], "status": existing["status"], "duplicate": True}
            supersedes = value.get("supersedes")
            if supersedes is not None:
                if not isinstance(supersedes, str):
                    raise ReviewError("supersedes must be a stored quiz set ID.")
                old = _set(data, supersedes)
                if not old.get("manifest") or binding(old["manifest"]) != binding(manifest):
                    raise ReviewError("A corrected set must supersede a set for the same target/content binding.")
            # Recheck while holding the writer lock; no partially imported set is visible.
            if currentness(repo, manifest) != "current":
                raise ReviewError("HEAD content changed during import; retry with a fresh export.")
            set_id = uuid.uuid4().hex
            data["sets"][set_id] = {"id": set_id, "status": "validated", "manifest": manifest,
                "validation_version": 1,
                "questions": questions, "generator": generator, "fingerprint": fingerprint,
                "binding": binding(manifest), "supersedes": supersedes,
                "imported_at": now.isoformat(), "import_sequence": sequence(data)}
            return {"set_id": set_id, "status": "validated", "duplicate": False,
                    "question_count": len(questions), "key_quality": "shape validated; key correctness unproven"}

    def start(self, set_id: str, now: datetime, practice: bool = False) -> dict:
        # Guard before creating a lock/directory, then validate again under lock.
        self._guard_set(_set(self.store.read(), set_id))
        with self.store.transaction() as data:
            quiz = _set(data, set_id)
            repo = _require_current(quiz)
            self.store.guard(repo.root)
            attempts = sorted((a for a in data["attempts"].values() if a["set_id"] == set_id),
                              key=lambda a: a["ordinal"])
            if attempts and not practice:
                return {"attempt_id": attempts[0]["id"], "resumed": True,
                        "completed": attempts[0]["completed_at"] is not None}
            if practice and (not attempts or attempts[0]["completed_at"] is None):
                raise ReviewError("Complete the first attempt before starting practice.")
            attempt_id = uuid.uuid4().hex
            data["attempts"][attempt_id] = {"id": attempt_id, "set_id": set_id,
                "ordinal": len(attempts) + 1, "eligible_first_attempt": not attempts and not practice,
                "started_at": now.isoformat(), "completed_at": None, "completed_sequence": None,
                "answers": {}}
            sequence(data)
            return {"attempt_id": attempt_id, "resumed": False, "completed": False}

    def show(self, attempt_id: str) -> dict:
        attempt, quiz = _attempt(self.store.read(), attempt_id)
        repo = _require_current(quiz)
        self.store.guard(repo.root)
        if attempt["completed_at"]:
            raise ReviewError("Attempt is complete; use quiz results to view its key and explanations.")
        manifest = quiz["manifest"]
        source = manifest["target"]
        return {"attempt_id": attempt_id, "set_id": quiz["id"], "ordinal": attempt["ordinal"],
            "eligible_first_attempt": attempt["eligible_first_attempt"], "conditions": "open-book",
            "target": {**source, "code": block(repo, manifest["source_revision"], source["path"],
                                                source["start_line"], source["end_line"])["code"]},
            "context": [{**c, "code": block(repo, manifest["source_revision"], c["path"],
                                           c["start_line"], c["end_line"])["code"]} for c in manifest["context"]],
            "questions": [{"id": q["id"], "prompt": q["prompt"], "options": q["options"],
                           "submitted": q["id"] in attempt["answers"]} for q in quiz["questions"]],
            "confidence_choices": list(CONFIDENCE)}

    def answer(self, attempt_id: str, question_id: str, chosen_index: int, confidence: str,
               now: datetime) -> dict:
        if type(chosen_index) is not int or not 0 <= chosen_index < 4 or confidence not in CONFIDENCE:
            raise ReviewError("Answer requires an option index 0–3 and solid/shaky/guessed confidence.")
        self._guard_set(_attempt(self.store.read(), attempt_id)[1])
        with self.store.transaction() as data:
            attempt, quiz = _attempt(data, attempt_id)
            repo = _require_current(quiz)
            self.store.guard(repo.root)
            if question_id not in {q["id"] for q in quiz["questions"]}:
                raise ReviewError("Unknown question ID for this attempt.")
            existing = attempt["answers"].get(question_id)
            if existing:
                if (existing["chosen_index"], existing["confidence"]) != (chosen_index, confidence):
                    raise ReviewError("Submitted answers are immutable; this replacement conflicts with the first answer.")
                return {"accepted": True, "idempotent": True}
            if attempt["completed_at"]:
                raise ReviewError("Cannot add answers to a completed attempt.")
            attempt["answers"][question_id] = {"chosen_index": chosen_index, "confidence": confidence,
                                                "submitted_at": now.isoformat()}
            sequence(data)
            return {"accepted": True, "idempotent": False}

    def complete(self, attempt_id: str, now: datetime) -> dict:
        self._guard_set(_attempt(self.store.read(), attempt_id)[1])
        with self.store.transaction() as data:
            attempt, quiz = _attempt(data, attempt_id)
            repo = _require_current(quiz)
            self.store.guard(repo.root)
            if len(attempt["answers"]) != len(quiz["questions"]):
                raise ReviewError("Answer every question before completing; keys remain withheld.")
            if not attempt["completed_at"]:
                attempt["completed_at"] = now.isoformat()
                attempt["completed_sequence"] = sequence(data)
        return self.results(attempt_id)

    def results(self, attempt_id: str) -> dict:
        attempt, quiz = _attempt(self.store.read(), attempt_id)
        if not attempt["completed_at"]:
            raise ReviewError("Keys and correctness remain withheld until the whole attempt is complete.")
        repo = Repository(Path(quiz["manifest"]["checkout"]))
        self.store.guard(repo.root)
        grades = _grades(quiz, attempt)
        status = currentness(repo, quiz["manifest"])
        summary = self.status(repo)
        target = next(t for t in summary["files"][quiz["manifest"]["target"]["path"]]["targets"]
                      if t["binding"] == binding(quiz["manifest"]))
        return {"attempt_id": attempt_id, "set_id": quiz["id"], "ordinal": attempt["ordinal"],
            "eligible_first_attempt": attempt["eligible_first_attempt"], "completed_at": attempt["completed_at"],
            "currentness": status, "set_status": quiz["status"],
            "passed_against_key": all(g["correct"] for g in grades),
            "sample_pass_eligible": attempt["eligible_first_attempt"] and quiz["status"] == "validated" and status == "current",
            "effective_status": target["status"],
            "current_sample_pass": attempt_id in target["current_pass_attempts"],
            "scope": "target sample; agreement with stored key, not whole-file understanding",
            "questions": [{**g, "prompt": q["prompt"], "options": q["options"],
                           "correct_index": q["correct_index"], "explanation": q["explanation"],
                           "rationale": q["rationale"]} for q, g in zip(quiz["questions"], grades)]}

    def reject(self, set_id: str, reason: str, now: datetime) -> dict:
        reason = text(reason, "Rejection reason")
        self._guard_set(_set(self.store.read(), set_id))
        with self.store.transaction() as data:
            quiz = _set(data, set_id)
            if quiz.get("manifest"):
                self.store.guard(Path(quiz["manifest"]["checkout"]))
            quiz.update(status="rejected", reason=reason, rejected_at=now.isoformat(),
                        rejection_sequence=sequence(data))
        return {"set_id": set_id, "status": "rejected", "reason": reason,
                "history_preserved": True}

    def feedback(self, attempt_id: str, now: datetime, *, purpose: str, useful: str = "unreported",
                 familiarity: str | None = None, active_minutes: float | None = None,
                 note: str = "") -> dict:
        if purpose not in PURPOSES or useful not in USEFULNESS or (
            familiarity is not None and familiarity not in FAMILIARITY):
            raise ReviewError("Choose a valid review purpose, usefulness, and familiarity.")
        if active_minutes is not None and (type(active_minutes) not in {int, float} or
            not math.isfinite(active_minutes) or not 0 <= active_minutes <= 1440):
            raise ReviewError("Active minutes must be finite and between 0 and 1440.")
        if not isinstance(note, str) or len(note) > 4000:
            raise ReviewError("Feedback note must be text of at most 4000 characters.")
        attempt, quiz = _attempt(self.store.read(), attempt_id)
        self._guard_set(quiz)
        if not attempt["completed_at"]:
            raise ReviewError("Complete the attempt before recording experiment feedback.")
        payload = {"attempt_id": attempt_id, "purpose": purpose, "useful": useful,
                   "prior_familiarity": familiarity, "active_minutes": active_minutes, "note": note.strip()}
        with self.store.transaction() as data:
            attempt, quiz = _attempt(data, attempt_id)
            self._guard_set(quiz)
            previous = next((f for f in reversed(data["feedback"]) if f["attempt_id"] == attempt_id), None)
            if previous and all(previous.get(k) == v for k, v in payload.items()):
                return {"feedback_id": previous["id"], "recorded": True, "idempotent": True}
            event = {**payload, "id": uuid.uuid4().hex, "recorded_at": now.isoformat(),
                     "sequence": sequence(data)}
            data["feedback"].append(event)
        return {"feedback_id": event["id"], "recorded": True, "idempotent": False,
                "scope": "experiment annotation; answers, grades, and passes unchanged"}

    def status(self, repo: Repository) -> dict:
        self.store.guard(repo.root)
        data = self.store.read()
        quizzes = [q for q in data["sets"].values() if q.get("manifest") and
                   q["manifest"]["checkout"] == str(repo.root)]
        groups = {}
        summaries = []
        historical_wrong = 0
        for quiz in quizzes:
            state = currentness(repo, quiz["manifest"])
            summaries.append({"set_id": quiz["id"], "path": quiz["manifest"]["target"]["path"],
                "target": quiz["manifest"]["target"]["key"], "status": quiz["status"],
                "currentness": state, "reason": quiz.get("reason")})
            key = binding(quiz["manifest"])
            group = groups.setdefault(key, {"path": quiz["manifest"]["target"]["path"],
                "target": quiz["manifest"]["target"]["key"], "binding": key,
                "currentness": state, "attempted": False, "passes": [], "wrongs": []})
            if quiz["status"] == "validated" and state == "current":
                group["currentness"] = "current"
            for attempt in data["attempts"].values():
                if attempt["set_id"] != quiz["id"]:
                    continue
                if quiz["status"] == "validated":
                    group["attempted"] = True
                if not attempt["completed_at"] or quiz["status"] != "validated":
                    continue
                grades = _grades(quiz, attempt)
                wrong = sum(not g["correct"] and g["confidence"] == "solid" for g in grades)
                historical_wrong += wrong
                record = {"sequence": attempt["completed_sequence"], "set_id": quiz["id"],
                          "attempt_id": attempt["id"], "currentness": state}
                if wrong:
                    group["wrongs"].append({**record, "count": wrong})
                if attempt["eligible_first_attempt"] and all(g["correct"] for g in grades):
                    group["passes"].append(record)
        targets = []
        for group in groups.values():
            current = group["currentness"] == "current"
            wrongs = [w for w in group["wrongs"] if not current or w["currentness"] == "current"]
            passes = [p for p in group["passes"] if not current or p["currentness"] == "current"]
            last_wrong = max((w["sequence"] for w in wrongs), default=-1)
            last_pass = max((p["sequence"] for p in passes), default=-1)
            active_passes = [p for p in passes if p["sequence"] > last_wrong]
            wrong_count = sum(w["count"] for w in wrongs if w["sequence"] > last_pass)
            status = (group["currentness"] if not current else "sample_passed" if active_passes else
                      "revoked" if group["passes"] and group["wrongs"] else
                      "attempted" if group["attempted"] else "unattempted")
            targets.append({"path": group["path"], "target": group["target"], "binding": group["binding"],
                "status": status, "current_passing_samples": len(active_passes) if current else 0,
                "current_pass_attempts": [p["attempt_id"] for p in active_passes] if current else [],
                "current_confidently_wrong": wrong_count if current else 0,
                "historical_confidently_wrong": sum(w["count"] for w in group["wrongs"]),
                "revoked_samples": len(group["passes"]) - len(active_passes),
                "revocation_causes": [w["set_id"] for w in group["wrongs"] if w["sequence"] >
                                      min((p["sequence"] for p in group["passes"]), default=float("inf"))]})
        files = {}
        for target in targets:
            summary = files.setdefault(target["path"], {"current_passing_samples": 0, "targets": []})
            summary["current_passing_samples"] += target["current_passing_samples"]
            summary["targets"].append(target)
        set_ids = {q["id"] for q in quizzes}
        completed = {a["id"]: a for a in data["attempts"].values()
                     if a["set_id"] in set_ids and a["completed_at"]}
        feedback = [f for f in data["feedback"] if f["attempt_id"] in completed]
        latest = {f["attempt_id"]: f for f in feedback}
        understanding = [f for f in latest.values() if f["purpose"] == "understanding-review"]
        experiment = {"completed_attempts": len(completed),
            "workflow_test_attempts": sum(f["purpose"] == "workflow-test" for f in latest.values()),
            "understanding_review_attempts": len(understanding),
            "unclassified_completed_attempts": len(completed) - len(latest),
            "distinct_targets_with_understanding_feedback": len({
                binding(data["sets"][completed[f["attempt_id"]]["set_id"]]["manifest"]) for f in understanding}),
            "usefulness": {key: sum(f["useful"] == key for f in understanding) for key in USEFULNESS},
            "scope": "self-reported experiment feedback; includes practice and disputed-set feedback; not a release gate"}
        return {"checkout": str(repo.root), "head": repo.head, "files": files,
                "sets": summaries, "current_confidently_wrong": sum(t["current_confidently_wrong"] for t in targets),
                "historical_confidently_wrong": historical_wrong,
                "feedback": feedback, "experiment": experiment,
                "scope": "target samples only; evidence states are unchanged"}
