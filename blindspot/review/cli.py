from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path

from ..scan.repo import Repository
from ..scan.report import safe
from . import ReviewError
from .service import CONFIDENCE, FAMILIARITY, PURPOSES, USEFULNESS, ReviewService
from .targets import export_target


def add_commands(commands, common):
    target = commands.add_parser("target", parents=[common], help="export explicit committed source for a review")
    sub = target.add_subparsers(dest="target_command", required=True)
    export = sub.add_parser("export", parents=[common])
    export.add_argument("file", type=Path)
    export.add_argument("--start", type=int)
    export.add_argument("--end", type=int)
    export.add_argument("--name")
    export.add_argument("--context", action="append", type=Path, default=[])
    export.add_argument("--context-range", action="append", nargs=3, default=[], metavar=("FILE", "START", "END"))
    export.add_argument("--output", type=Path)
    quiz = commands.add_parser("quiz", parents=[common], help="import, answer, and dispute target quizzes")
    sub = quiz.add_subparsers(dest="quiz_command", required=True)
    imported = sub.add_parser("import", parents=[common])
    imported.add_argument("file", type=Path)
    for name in ("start", "review"):
        command = sub.add_parser(name, parents=[common])
        command.add_argument("set_id")
        command.add_argument("--practice", action="store_true")
    for name in ("show", "complete", "results"):
        command = sub.add_parser(name, parents=[common])
        command.add_argument("attempt_id")
    answer = sub.add_parser("answer", parents=[common])
    answer.add_argument("attempt_id")
    answer.add_argument("question_id")
    answer.add_argument("--choice", type=int, choices=(1, 2, 3, 4), required=True)
    answer.add_argument("--confidence", choices=CONFIDENCE, required=True)
    reject = sub.add_parser("reject", parents=[common])
    reject.add_argument("set_id")
    reject.add_argument("--reason", required=True)
    feedback = sub.add_parser("feedback", parents=[common], help="record experiment purpose and usefulness")
    feedback.add_argument("attempt_id")
    feedback.add_argument("--purpose", choices=PURPOSES, required=True)
    feedback.add_argument("--useful", choices=USEFULNESS, default="unreported")
    feedback.add_argument("--familiarity", choices=FAMILIARITY)
    feedback.add_argument("--active-minutes", type=float)
    feedback.add_argument("--note", default="")
    status = sub.add_parser("status", parents=[common])
    status.add_argument("path", type=Path, nargs="?", default=Path.cwd())


def load_json(path: Path):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ReviewError("Quiz JSON contains a repeated object key.")
            result[key] = value
        return result
    if path.stat().st_size > 256 * 1024:
        raise ReviewError("Quiz JSON exceeds the 256 KiB import limit.")
    try:
        return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=pairs)
    except (ValueError, UnicodeError):
        raise ReviewError("Quiz import requires valid UTF-8 JSON without repeated keys.") from None


def interactive(service: ReviewService, set_id: str, now: datetime, practice: bool) -> dict:
    started = service.start(set_id, now, practice)
    attempt = started["attempt_id"]
    if started["completed"]:
        return service.results(attempt)
    view = service.show(attempt)
    print("Open-book target review. Keys and explanations appear after every answer is submitted.")
    if not view["eligible_first_attempt"]:
        print("Practice attempt: cannot earn a first-attempt sample pass.")
    for source in [view["target"], *view["context"]]:
        print(f"\n{safe(source['path'])}:{source['start_line']}-{source['end_line']}")
        for number, line in enumerate(source["code"].splitlines(), source["start_line"]):
            print(f"{number:4} {safe(line)}")
    for question in view["questions"]:
        if question["submitted"]:
            print(f"\n{question['id']}: previously submitted; answer preserved.")
            continue
        print(f"\n{question['id']}: {safe(question['prompt'])}")
        for index, option in enumerate(question["options"], 1):
            print(f"  {index}. {safe(option)}")
        while True:
            choice = input("Choice [1-4; q to pause]: ").strip()
            if choice.lower() == "q":
                raise EOFError()
            if choice in {"1", "2", "3", "4"}:
                break
            print("Enter 1, 2, 3, or 4.")
        while True:
            confidence = input("Confidence [solid/shaky/guessed]: ").strip().lower()
            if confidence in CONFIDENCE:
                break
            print("Enter solid, shaky, or guessed.")
        service.answer(attempt, question["id"], int(choice) - 1, confidence, datetime.now(now.tzinfo))
        print("Answer recorded.")
    return service.complete(attempt, datetime.now(now.tzinfo))


def run(args, directory: Path, now: datetime, read_only: bool) -> int:
    if args.command == "target":
        if read_only and args.output:
            raise ReviewError("--read-only target export writes only to stdout; omit --output.")
        contexts = [(p, None, None) for p in args.context]
        contexts.extend((Path(p), int(a), int(b)) for p, a, b in args.context_range)
        manifest = export_target(args.file, args.start, args.end, args.name, contexts)
        output = json.dumps(manifest, indent=2, ensure_ascii=True) + "\n"
        if args.output:
            destination = args.output.expanduser().resolve()
            if destination.is_relative_to(Path(manifest["checkout"])):
                raise ReviewError("Export to a location outside the inspected checkout.")
            if destination.exists():
                raise ReviewError("Export output already exists; choose a new path.")
            with destination.open("x", encoding="utf-8") as handle:
                handle.write(output)
            print(json.dumps({"exported": str(destination), "target": manifest["target"]["key"]}))
        else:
            print(output, end="")
        return 0
    mutating = {"import", "start", "review", "answer", "complete", "reject", "feedback"}
    if read_only and args.quiz_command in mutating:
        raise ReviewError("--read-only supports quiz status, show, and results; review mutations require writes.")
    service = ReviewService(directory, read_only)
    command = args.quiz_command
    if command == "import":
        result = service.import_quiz(load_json(args.file.expanduser()), now)
    elif command in {"start", "review"}:
        result = (interactive(service, args.set_id, now, args.practice) if command == "review"
                  else service.start(args.set_id, now, args.practice))
    elif command == "show":
        result = service.show(args.attempt_id)
    elif command == "answer":
        result = service.answer(args.attempt_id, args.question_id, args.choice - 1, args.confidence, now)
    elif command == "complete":
        result = service.complete(args.attempt_id, now)
    elif command == "results":
        result = service.results(args.attempt_id)
    elif command == "reject":
        result = service.reject(args.set_id, args.reason, now)
    elif command == "feedback":
        result = service.feedback(args.attempt_id, now, purpose=args.purpose, useful=args.useful,
                                  familiarity=args.familiarity, active_minutes=args.active_minutes, note=args.note)
    else:
        result = service.status(Repository(args.path.expanduser()))
    if command == "review":
        print(f"\nAttempt: {result['attempt_id']}")
        print(f"Target status: {result['effective_status']}; current sample pass: {result['current_sample_pass']}")
        print(result["scope"])
        for q in result["questions"]:
            correct = "correct against key" if q["correct"] else "incorrect against key"
            print(f"\n{q['question_id']}: selected {q['chosen_index'] + 1}; key {q['correct_index'] + 1}; "
                  f"{q['confidence']}, {correct}")
            print(safe(q["explanation"]))
            rationale = q["rationale"]
            print(f"Source: {safe(rationale['path'])}:{rationale['start_line']}-{rationale['end_line']} — "
                  f"{safe(rationale['reason'])}")
    else:
        print(json.dumps(result, indent=2, ensure_ascii=True))
    return 2 if command == "import" and result["status"] == "rejected" else 0
