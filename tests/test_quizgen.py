from datetime import datetime, timezone
import json

from blindspot.observer.dashboard import Dashboard
from blindspot.observer.quizgen import QuizError, choose_range, extract_json, grounding_warnings, normalize
from blindspot.observer.sqlite_store import SQLiteStore
from blindspot.observer.store import digest
from blindspot.review import ReviewError
from .support import SandboxCase
from .test_guide import PY


def question(**over):
    base = {"prompt": "What does get do with an empty url?", "options": ["Returns None", "Raises ValueError", "Fetches anyway", "Loops"],
            "correct_index": 1, "explanation": "It raises ValueError.", "rationale": {"path": "m.py", "start_line": 24, "end_line": 25, "reason": "The check on line 24."}}
    return {**base, **over}


def reply(count=3, **over):
    return json.dumps({"questions": [question(prompt=f"Question {i}?", **over) for i in range(count)]})


class ChooseRangeTests(SandboxCase):
    def test_short_units_grow_and_long_units_are_windowed(self):
        text = "".join(f"line {n}\n" for n in range(1, 101))
        start, end, note = choose_range(text, {"start": 50, "end": 53, "unseen_ranges": []})
        self.assertEqual(end - start + 1, 10); self.assertLessEqual(start, 50); self.assertGreaterEqual(end, 53); self.assertIn("nearby", note)
        start, end, _ = choose_range(text, {"start": 98, "end": 100, "unseen_ranges": []})
        self.assertEqual((start, end), (91, 100))
        big = "".join(f"line {n}\n" for n in range(1, 701))
        start, end, note = choose_range(big, {"start": 1, "end": 700, "unseen_ranges": [[400, 650]]})
        self.assertEqual((start, end), (400, 699)); self.assertIn("covers lines", note)
        wide = "".join("x" * 200 + "\n" for _ in range(200))
        start, end, _ = choose_range(wide, {"start": 1, "end": 200, "unseen_ranges": []})
        self.assertLessEqual(len("".join(wide.splitlines(keepends=True)[start - 1:end]).encode()), 16 * 1024)
        with self.assertRaises(QuizError): choose_range("a\nb\n", {"start": 1, "end": 2, "unseen_ranges": []})


    def test_long_unit_gap_at_end_still_selects_ten_lines(self):
        text = "".join(f"line {n}\n" for n in range(1, 701))
        start, end, _ = choose_range(text, {"start": 1, "end": 700, "unseen_ranges": [[699, 700]]})
        self.assertEqual((start, end), (691, 700))
        with self.assertRaisesRegex(QuizError, "size limit"):
            choose_range("x" * 2000 + "\n" + ("x" * 2000 + "\n") * 10,
                         {"start": 1, "end": 11, "unseen_ranges": []})


class ReplyParsingTests(SandboxCase):
    def parse(self, text): return normalize(text, "m.py", 20, 29)

    def test_accepts_fences_prose_bare_lists_and_common_variants(self):
        self.assertEqual(len(self.parse("Sure! Here you go:\n```json\n" + reply() + "\n```\nHope it helps.")), 3)
        self.assertEqual(len(self.parse(json.dumps([question(prompt=f"Q{i}?") for i in range(3)]))), 3)
        loose = {"question": "Which?", "choices": ["A) one", "B) two", "C) three", "D) four"], "answer": "C",
                 "explanation": "Because.", "rationale": {"start_line": "22", "end_line": "24", "reason": "r"}}
        [q] = self.parse(json.dumps({"questions": [loose]}))
        self.assertEqual((q["options"], q["correct_index"], q["rationale"]["path"]), (["one", "two", "three", "four"], 2, "m.py"))
        by_text = {**loose, "answer": "two", "choices": ["one", "two", "three", "four"]}
        self.assertEqual(self.parse(json.dumps([by_text]))[0]["correct_index"], 1)

    def test_rejects_unusable_replies_with_a_specific_message(self):
        cases = [("", "Paste"), ("no json here", "valid JSON"), ('{"questions": []}', "no \"questions\""),
                 (reply(options=["a", "b"]), "4 text options"), (reply(correct_index=7), "0 to 3"),
                 (reply(rationale={"path": "m.py", "start_line": 1, "end_line": 5, "reason": "r"}), "outside the quiz range"),
                 (reply(rationale={"reason": "r"}), "start_line"), (json.dumps({"questions": ["text"]}), "not an object")]
        for text, expected in cases:
            with self.assertRaisesRegex(QuizError, expected): self.parse(text)

    def test_numbers_in_the_key_are_not_guessed_from_one_based_answers(self):
        loose = {**question(), "answer": 2}
        del loose["correct_index"]
        with self.assertRaises(QuizError): self.parse(json.dumps([loose, loose, loose]))

    def test_grounding_warnings_name_missing_identifiers(self):
        qs = [question(explanation="It calls `fetch` and `sleep_forever`."), question(explanation="Plain words.")]
        warnings = grounding_warnings(qs, "def get(url):\n    return fetch(url)\n")
        self.assertEqual(len(warnings), 1)
        self.assertIn("sleep_forever", warnings[0]); self.assertNotIn("`fetch`", warnings[0])
        self.assertEqual(extract_json("[1]"), [1])


class QuizFlowTests(SandboxCase):
    def setUp(self):
        super().setUp()
        self.root = self.root.resolve()
        self.commit({"m.py": PY})
        self.store = SQLiteStore(self.base / "observer", self.root); self.addCleanup(self.store.close)
        self.dashboard = Dashboard(self.store, self.state_dir)
        self.body = {"path": "m.py", "hash": digest(PY), "start": 23, "end": 26}

    def available(self):
        return next(f for f in self.dashboard.overview()["files"] if f["path"] == "m.py")["review"]["available"]

    def test_prompt_contains_only_the_quiz_range_and_the_rules(self):
        result = self.dashboard.quiz_prompt(self.body)
        self.assertEqual((result["question_count"], result["end"] - result["start"] + 1), (3, 10))
        prompt = result["prompt"]
        self.assertIn("exactly 3 questions", prompt); self.assertIn("correct_index is 0-based", prompt)
        self.assertIn("raise ValueError", prompt); self.assertIn(f"{result['start']:>5}|", prompt)
        self.assertIn("23-26", prompt)  # the never-seen lines are named
        self.assertNotIn("PRIVATE", prompt)

    def test_paste_creates_a_quiz_that_can_be_taken_and_reported(self):
        imported = self.dashboard.quiz_import({**self.body, "reply": "Here:\n" + reply()})
        self.assertEqual((imported["question_count"], imported["duplicate"]), (3, False))
        self.assertIn("not verified", imported["key_quality"])
        [offer] = self.available()
        self.assertEqual(offer["set_id"], imported["set_id"])
        attempt = self.dashboard.review_post("start", {"set_id": imported["set_id"]})["attempt_id"]
        for n in (1, 2, 3):
            self.dashboard.review_post("answer", {"attempt_id": attempt, "question_id": f"q{n}", "chosen_index": 1, "confidence": "solid"})
        done = self.dashboard.review_post("complete", {"attempt_id": attempt})
        self.assertTrue(done["passed_against_key"])
        self.assertEqual(self.dashboard.overview()["review"]["completed_attempts"], 1)
        again = self.dashboard.quiz_import({**self.body, "reply": reply()})
        self.assertTrue(again["duplicate"])
        self.dashboard.review_report({"attempt_id": attempt, "question_id": "q2"})
        overview = self.dashboard.overview()
        self.assertEqual(overview["review"]["completed_attempts"], 0)  # a reported set no longer counts
        self.assertEqual(self.available(), [])
        stored = self.dashboard.reviews.store.read()["sets"][imported["set_id"]]
        self.assertEqual(stored["status"], "rejected"); self.assertIn("question 2", stored["reason"])

    def test_bad_input_creates_nothing(self):
        for text in ("not json", reply(correct_index=9), reply(count=2)):
            with self.assertRaises((QuizError, ReviewError)): self.dashboard.quiz_import({**self.body, "reply": text})
        self.assertEqual(self.dashboard.reviews.store.read()["sets"], {})
        with self.assertRaises(ValueError): self.dashboard.quiz_import({**self.body, "start": 1, "end": 2, "reply": reply()})
        with self.assertRaises(ValueError): self.dashboard.quiz_prompt({**self.body, "hash": "stale"})
        with self.assertRaises(ValueError): self.dashboard.quiz_prompt({"path": "m.py"})
        with self.assertRaises(ReviewError): self.dashboard.review_report({"attempt_id": "nope", "question_id": "q1"})

    def test_uncommitted_files_cannot_have_quizzes(self):
        (self.root / "m.py").write_text(PY + "EXTRA = 1\n")
        body = {**self.body, "hash": digest(PY + "EXTRA = 1\n")}
        with self.assertRaisesRegex(QuizError, "uncommitted changes"): self.dashboard.quiz_prompt(body)
        (self.root / "new.py").write_text("x = 1\n" * 12)
        with self.assertRaisesRegex(QuizError, "not committed yet"):
            self.dashboard.quiz_prompt({"path": "new.py", "hash": digest("x = 1\n" * 12), "start": 1, "end": 12})

    def test_routes_require_a_local_origin_and_return_readable_errors(self):
        import threading
        from urllib.error import HTTPError
        from urllib.request import Request, urlopen
        from blindspot.observer.server import make_server
        server = make_server(self.store, "token", 0, review_directory=self.state_dir)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close); self.addCleanup(server.shutdown)
        endpoint = f"http://127.0.0.1:{server.server_address[1]}"
        def post(path, body, origin=True):
            headers = {"Content-Type": "application/json", **({"Origin": endpoint} if origin else {})}
            return urlopen(Request(endpoint + path, data=json.dumps(body).encode(), headers=headers), timeout=10)
        with self.assertRaises(HTTPError) as error: post("/api/dashboard/quiz/prompt", self.body, origin=False)
        self.assertEqual(error.exception.code, 403)
        with post("/api/dashboard/quiz/prompt", self.body) as response: self.assertIn("exactly 3 questions", json.load(response)["prompt"])
        with self.assertRaises(HTTPError) as error: post("/api/dashboard/quiz/import", {**self.body, "reply": "nope"})
        self.assertEqual(error.exception.code, 409); self.assertIn("valid JSON", json.loads(error.exception.read())["error"])
        with post("/api/dashboard/quiz/import", {**self.body, "reply": reply()}) as response: self.assertEqual(json.load(response)["question_count"], 3)
