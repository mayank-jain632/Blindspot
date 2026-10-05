"""Read models for the local dashboard; keys stay inside ReviewService."""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import subprocess

from ..review import ReviewError
from ..review.service import ReviewService
from ..review.targets import binding
from ..scan.repo import RepoError, Repository
from .guide import blame, build as build_guide
from .visibility import current_files, current_source, file_stats

STATES = {
    "current document state uncertain": "uncertain",
    "no matching display evidence": "no_evidence",
    "brief display only": "brief",
    "some current lines have no evidence": "partial",
    "reported across all eligible lines": "reported",
}
RANKING = ("Unresolved confidently-wrong samples first, then uncertain documents. "
           "Unverified display gaps are ordered by commits in 90 days, then missing lines. "
           "Current passing samples lower priority; display counts remain unchanged.")


def git_context(workspace, paths, now):
    env = {**os.environ, "GIT_OPTIONAL_LOCKS": "0"}
    def run(*args):
        return subprocess.run(["git", "-C", str(workspace), *args], capture_output=True,
                              env=env, timeout=5)
    counts = dict.fromkeys(paths, None)
    try:
        head = run("rev-parse", "--verify", "HEAD")
        branch = run("symbolic-ref", "--short", "-q", "HEAD")
        revision = head.stdout.decode().strip() if head.returncode == 0 else None
        if revision:
            result = run("log", revision, "--since=" + (now - timedelta(days=90)).isoformat(),
                         "--format=%x00BS_COMMIT%x00%H%x00", "--name-status", "-z", "--no-renames")
            if result.returncode == 0 and len(result.stdout) <= 2 * 1024 * 1024:
                counts = dict.fromkeys(paths, 0)
                tokens = result.stdout.split(b"\0"); index = 0; seen = set()
                while index < len(tokens):
                    token = tokens[index].lstrip(b"\n"); index += 1
                    if not token: continue
                    if token == b"BS_COMMIT":
                        index += 1; seen = set(); continue
                    if index >= len(tokens): break
                    path = os.fsdecode(tokens[index]); index += 1
                    if path in counts and path not in seen:
                        counts[path] += 1; seen.add(path)
        return {"revision": revision, "branch": branch.stdout.decode().strip() or "detached", "commits": counts}
    except (OSError, subprocess.TimeoutExpired):
        return {"revision": None, "branch": None, "commits": counts}


def priority(file):
    review = file["review"]
    tier = (0 if review["confidently_wrong"] else 1 if file["current_uncertain"] else
            4 if review["passing_samples"] else 2 if file["unknown_lines"] or not file["dwell_lines"] else 3)
    return (tier, -(file["commits_90d"] or 0), -file["unknown_lines"], file["path"])


class Dashboard:
    def __init__(self, store, review_directory: Path | None = None):
        self.store = store
        self.reviews = ReviewService(review_directory or store.directory)
        self.reviews.store.guard(store.workspace)

    def _matching(self, quiz, files):
        manifest = quiz.get("manifest")
        return bool(manifest and manifest["checkout"] == str(self.store.workspace) and
                    all(s["path"] in files and not files[s["path"]]["current_uncertain"] and
                        files[s["path"]]["content_hash"] == s["file_hash"]
                        for s in [manifest["target"], *manifest["context"]]))

    def overview(self):
        with self.store.lock:
            overview = self.store.overview()
            files = {f["path"]: f for f in overview["files"]}
            review_error = None
            try: data = self.reviews.store.read()
            except ReviewError as exc:
                data = {"sets": {}, "attempts": {}}
                review_error = str(exc)
            quizzes = {k: q for k, q in data["sets"].items() if q.get("manifest") and
                       q["manifest"]["checkout"] == str(self.store.workspace)}
            summary = {"files": {}, "sets": []}
            if quizzes:
                try: summary = self.reviews.status(Repository(self.store.workspace))
                except (ReviewError, RepoError) as exc: review_error = str(exc)
            statuses = {s["set_id"]: s for s in summary["sets"]}
            matching = {k: q for k, q in quizzes.items() if q["status"] == "validated" and
                        statuses.get(k, {}).get("currentness") == "current" and self._matching(q, files)}
            completed = [a for a in data["attempts"].values() if a["set_id"] in quizzes and
                         quizzes[a["set_id"]]["status"] == "validated" and a["completed_at"]]
            current_completed = [a for a in completed if a["set_id"] in matching]
            now = datetime.now(timezone.utc)
            git = git_context(self.store.workspace, files, now)
            calibration = {c: {"answers": 0, "correct": 0} for c in ("guessed", "shaky", "solid")}
            review_ticks = []
            for a in completed:
                q = quizzes[a["set_id"]]
                for question in q["questions"]:
                    answer = a["answers"][question["id"]]
                    calibration[answer["confidence"]]["answers"] += 1
                    calibration[answer["confidence"]]["correct"] += answer["chosen_index"] == question["correct_index"]
                review_ticks.append({"path": q["manifest"]["target"]["path"], "at": a["completed_at"], "attempt_id": a["id"]})
            for file in files.values():
                path = file["path"]
                bindings = {binding(q["manifest"]) for q in matching.values() if q["manifest"]["target"]["path"] == path}
                targets = [t for t in summary["files"].get(path, {}).get("targets", []) if t["binding"] in bindings]
                tested = [a for a in current_completed if quizzes[a["set_id"]]["manifest"]["target"]["path"] == path]
                available = []
                for key, quiz in matching.items():
                    if quiz["manifest"]["target"]["path"] != path: continue
                    attempts = [a for a in data["attempts"].values() if a["set_id"] == key and a["eligible_first_attempt"]]
                    if not attempts or not attempts[0]["completed_at"]:
                        available.append({"set_id": key, "start_line": quiz["manifest"]["target"]["start_line"],
                                          "end_line": quiz["manifest"]["target"]["end_line"], "question_count": len(quiz["questions"])})
                file["review"] = {"tested": bool(tested), "completed_attempts": len(tested),
                    "passing_samples": sum(t["current_passing_samples"] for t in targets),
                    "confidently_wrong": any(t["current_confidently_wrong"] for t in targets),
                    "tested_ranges": [[quizzes[a["set_id"]]["manifest"]["target"]["start_line"],
                                       quizzes[a["set_id"]]["manifest"]["target"]["end_line"]] for a in tested],
                    "available": available,
                    "stale_results": any(a for a in completed if quizzes[a["set_id"]]["manifest"]["target"]["path"] == path and a["set_id"] not in matching)}
                file["state"] = STATES[file["review_reason"]]
                file["commits_90d"] = git["commits"][path]
                file["flagged"] = bool(file["current_uncertain"] or file["unknown_lines"] or
                                       not file["dwell_lines"] or file["review"]["confidently_wrong"])
                file["evidence"] = self.evidence(file)
            ranked = sorted(files.values(), key=priority)
            for rank, file in enumerate(ranked, 1): file["rank"] = rank
            # Daily groups include every stored event; the lane window remains bounded.
            days = self.store.db.execute("SELECT substr(observed_at,1,10),path,COUNT(*) FROM events "
                                         "WHERE kind IN ('visibility','interaction','file_event') AND path IS NOT NULL GROUP BY 1,2").fetchall()
            weekly = defaultdict(Counter)
            touched = defaultdict(set)
            for day, path, count in days:
                date = datetime.fromisoformat(day)
                week = (date - timedelta(days=date.weekday())).date().isoformat()
                weekly[week]["event_count"] += count
                touched[week].add(path)
            return {**overview, "files": ranked, "queue": [f["path"] for f in ranked if f["flagged"]],
                    "has_observations": overview["health"]["storage"]["events"] > 0,
                    "git": {k: v for k, v in git.items() if k != "commits"}, "ranking": RANKING,
                    "review": {"error": review_error, "directory": str(self.reviews.store.directory),
                        "confidently_wrong_files": sum(f["review"]["confidently_wrong"] for f in ranked),
                        "completed_attempts": len(completed), "calibration": calibration,
                        "ticks": review_ticks},
                    "weekly": [{"week": w, "files_touched": len(touched[w]), **counts} for w, counts in sorted(weekly.items())],
                    "derivations": {"display": "Reported lines / eligible current lines; uncertain files excluded. Display evidence, not reading.",
                        "commits": "Distinct Git commits touching the current path in the last 90 days; no rename attribution.",
                        "wrong": "Distinct current files with at least one unresolved solid-confidence wrong answer on a matching target/context binding.",
                        "calibration": "Answers in completed validated quiz attempts for this workspace, including practice and historical source versions; agreement with stored keys.",
                        "weekly": "All stored visibility, interaction and filesystem notification records, grouped by observed date (UTC collector timestamps). Not edits or authorship."}}

    def evidence(self, file):
        records = []
        def add(text, source, state=None):
            records.append({"text": text, "source": source, "state": state or file["state"]})
        if file["current_uncertain"]:
            add("File status unknown. Reconnect the extension.", "SQLite documents + session liveness", "uncertain")
        else:
            add(f'{file["reported_lines"]} of {file["line_count"]} lines seen.',
                "SQLite visibility ranges + source hashes; unique unchanged-block mapping")
            add(f'{file["dwell_lines"]} lines on screen for at least a second.', "SQLite timed visibility intervals; per-session union, maximum across sessions")
            add(f'{file["unknown_lines"]} lines never on screen.', "Current source minus matched visibility ranges", "no_evidence")
        if file["interaction_events"]:
            add(f'{file["interaction_events"]} editor interactions.', "SQLite interaction records (all source versions)")
        if file["commits_90d"] is not None:
            add(f'{file["commits_90d"]} commits in 90 days.', "Git HEAD history; commit count, not edit count")
        review = file["review"]
        if review["tested"]:
            add(f'{review["completed_attempts"]} quizzes completed.', "reviews.json completed validated attempts + current source hashes", "sample_passed")
        else: add("No quiz taken for this version. Choose a quiz in Risk.", "reviews.json completed attempts + current source hashes", "no_evidence")
        if review["passing_samples"]:
            add(f'{review["passing_samples"]} samples passed. Priority lowered.', "ReviewService current_pass_attempts; sample scope only", "sample_passed")
        if review["confidently_wrong"]:
            add("You answered confidently and were wrong. Review this file again.", "ReviewService target.current_confidently_wrong", "uncertain")
        return records

    def source(self, path, expected_hash):
        return current_source(self.store, path, expected_hash)

    def guide(self, path, expected_hash):
        """Study guide for one file; structure and Git history only, no model."""
        with self.store.lock:
            files, _ = current_files(self.store)
            file = next((f for f in files if f["path"] == path), None)
            if not file: raise ValueError("File is outside the eligible current inventory")
            if file["current_uncertain"]: raise ValueError("Current document state is uncertain; resume recording and refresh")
            if file["content_hash"] != expected_hash: raise ValueError("Source changed since the overview; refresh before opening the guide")
            stats = file_stats(self.store, file)
            text, origin = file["text"], file["origin"]
        # Blame reads the saved file, so it only applies when the text came from disk.
        history = blame(self.store.workspace, path, len(text.split("\n"))) if origin == "disk" else None
        return build_guide(text, path, stats["reported_ranges"], history)

    def _require_binding(self, set_id):
        data = self.reviews.store.read()
        quiz = data["sets"].get(set_id)
        with self.store.lock:
            files, _ = current_files(self.store)
            if not quiz or quiz["status"] != "validated" or not self._matching(quiz, {f["path"]: f for f in files}):
                raise ReviewError("Quiz source or context is unavailable, changed, or uncertain. Refresh before reviewing.")
        return quiz

    def _require_attempt(self, attempt_id):
        attempt = self.reviews.store.read()["attempts"].get(attempt_id)
        if not attempt: raise ReviewError("Unknown attempt ID.")
        self._require_binding(attempt["set_id"])

    def review_get(self, action, attempt_id):
        self._require_attempt(attempt_id)
        if action == "attempt": return self.reviews.show(attempt_id)
        if action == "results": return self.reviews.results(attempt_id)
        raise ReviewError("Unknown review operation.")

    def review_post(self, action, body):
        if not isinstance(body, dict): raise ReviewError("JSON object required.")
        now = datetime.now(timezone.utc)
        if action == "start":
            self._require_binding(body.get("set_id"))
            return self.reviews.start(body["set_id"], now)
        attempt_id = body.get("attempt_id")
        self._require_attempt(attempt_id)
        if action == "answer":
            # The browser supplies IDs and the user's choice, never a key or grade.
            if set(body) != {"attempt_id", "question_id", "chosen_index", "confidence"}:
                raise ReviewError("Answer requires only attempt/question IDs, option index and confidence.")
            return self.reviews.answer(attempt_id, body["question_id"], body["chosen_index"], body["confidence"], now)
        if action == "complete": return self.reviews.complete(attempt_id, now)
        raise ReviewError("Unknown review operation.")
