"""Build a repeatable demo: a small sample project plus recorded display evidence.

    python3 scripts/seed_demo.py                # writes sandbox/demo
    .venv/bin/python -B -m blindspot observer serve \
        --workspace sandbox/demo/project --state-dir sandbox/demo/state --port 7777

The project is invented. Observations are generated so the dashboard shows a mix
of fully seen, partly seen and never-seen files, a few weeks of activity, and one
completed quiz. It never touches your real recording state.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import shutil
import subprocess
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from blindspot.observer.dashboard import Dashboard  # noqa: E402
from blindspot.observer.sqlite_store import SQLiteStore  # noqa: E402
from blindspot.observer.store import digest  # noqa: E402
from blindspot.review.targets import export_target  # noqa: E402

FILES = {
"catalog.py": '''"""In-memory catalog of books."""
from dataclasses import dataclass, field


@dataclass
class Book:
    isbn: str
    title: str
    author: str
    copies: int = 1
    tags: list = field(default_factory=list)


def valid_isbn(isbn: str) -> bool:
    digits = [c for c in isbn if c.isdigit()]
    if len(digits) != 13:
        return False
    total = sum(int(d) * (1 if i % 2 == 0 else 3) for i, d in enumerate(digits))
    return total % 10 == 0


class Catalog:
    def __init__(self):
        self.books = {}

    def add(self, book: Book) -> None:
        if not valid_isbn(book.isbn):
            raise ValueError(f"bad isbn: {book.isbn}")
        existing = self.books.get(book.isbn)
        if existing:
            existing.copies += book.copies
        else:
            self.books[book.isbn] = book

    def remove(self, isbn: str) -> Book:
        return self.books.pop(isbn)

    def by_author(self, name: str) -> list:
        needle = name.lower()
        return [b for b in self.books.values() if needle in b.author.lower()]
''',
"loans.py": '''"""Checking books out and back in."""
from datetime import date, timedelta

LOAN_DAYS = 21
MAX_RENEWALS = 2
MAX_ACTIVE = 5


class LoanError(Exception):
    pass


class Loan:
    def __init__(self, isbn: str, member: str, start: date):
        self.isbn = isbn
        self.member = member
        self.start = start
        self.due = start + timedelta(days=LOAN_DAYS)
        self.renewals = 0
        self.returned = None

    def renew(self, today: date) -> None:
        if self.returned:
            raise LoanError("already returned")
        if self.renewals >= MAX_RENEWALS:
            raise LoanError("renewal limit reached")
        if today > self.due:
            raise LoanError("overdue loans cannot be renewed")
        self.due += timedelta(days=LOAN_DAYS)
        self.renewals += 1


class Ledger:
    def __init__(self, catalog):
        self.catalog = catalog
        self.loans = []

    def active_for(self, member: str) -> list:
        return [l for l in self.loans if l.member == member and not l.returned]

    def checkout(self, isbn: str, member: str, today: date) -> Loan:
        book = self.catalog.books.get(isbn)
        if book is None:
            raise LoanError("unknown book")
        lent = sum(1 for l in self.loans if l.isbn == isbn and not l.returned)
        if lent >= book.copies:
            raise LoanError("no copies available")
        if len(self.active_for(member)) >= MAX_ACTIVE:
            raise LoanError("too many active loans")
        loan = Loan(isbn, member, today)
        self.loans.append(loan)
        return loan

    def give_back(self, loan: Loan, today: date) -> None:
        if loan.returned:
            raise LoanError("already returned")
        loan.returned = today
''',
"fines.py": '''"""Late fees. Amounts are in cents."""
from datetime import date

GRACE_DAYS = 3
DAILY_CENTS = 25
CAP_CENTS = 1500
WAIVER_BALANCE = 100


def days_late(due: date, returned: date) -> int:
    return max(0, (returned - due).days)


def fine_for(due: date, returned: date) -> int:
    late = days_late(due, returned)
    if late <= GRACE_DAYS:
        return 0
    # Once past the grace period, every late day counts, including the grace days.
    return min(CAP_CENTS, late * DAILY_CENTS)


def apply_waiver(balance_cents: int, member_in_good_standing: bool) -> int:
    if member_in_good_standing and balance_cents <= WAIVER_BALANCE:
        return 0
    return balance_cents


def summarize(fines: list) -> dict:
    total = sum(fines)
    return {
        "count": len(fines),
        "total_cents": total,
        "largest_cents": max(fines, default=0),
        "capped": sum(1 for f in fines if f >= CAP_CENTS),
    }
''',
"search.py": '''"""Very small full-text search over titles and authors."""
import re
from collections import Counter

STOP = {"the", "a", "an", "of", "and", "to", "in"}
TOKEN = re.compile(r"[a-z0-9']+")


def tokens(text: str) -> list:
    return [t for t in TOKEN.findall(text.lower()) if t not in STOP]


def score(query_tokens: list, book) -> float:
    title = Counter(tokens(book.title))
    author = Counter(tokens(book.author))
    value = 0.0
    for t in query_tokens:
        value += 3.0 * title[t] + 1.5 * author[t]
    return value


def search(catalog, query: str, limit: int = 10) -> list:
    wanted = tokens(query)
    if not wanted:
        return []
    ranked = sorted(((score(wanted, b), b) for b in catalog.books.values()), key=lambda p: -p[0])
    return [b for s, b in ranked if s > 0][:limit]
''',
"notifications.py": '''"""Reminder messages for members."""
from datetime import date

REMINDER_DAYS_BEFORE = 2


def due_soon(loans: list, today: date) -> list:
    return [l for l in loans if not l.returned and 0 <= (l.due - today).days <= REMINDER_DAYS_BEFORE]


def overdue(loans: list, today: date) -> list:
    return [l for l in loans if not l.returned and l.due < today]


def render(loan, today: date) -> str:
    left = (loan.due - today).days
    if left < 0:
        return f"{loan.member}: {loan.isbn} is {-left} days overdue."
    if left == 0:
        return f"{loan.member}: {loan.isbn} is due today."
    return f"{loan.member}: {loan.isbn} is due in {left} days."
''',
"cli.py": '''"""Command line entry point."""
import argparse
from datetime import date

from catalog import Book, Catalog
from loans import Ledger
from search import search


def main(argv=None):
    parser = argparse.ArgumentParser(prog="shelfmark")
    sub = parser.add_subparsers(dest="cmd", required=True)
    find = sub.add_parser("find")
    find.add_argument("query")
    out = sub.add_parser("checkout")
    out.add_argument("isbn")
    out.add_argument("member")
    args = parser.parse_args(argv)
    catalog = Catalog()
    catalog.add(Book("9780306406157", "The Pragmatic Programmer", "Hunt"))
    ledger = Ledger(catalog)
    if args.cmd == "find":
        for book in search(catalog, args.query):
            print(book.isbn, book.title)
    else:
        loan = ledger.checkout(args.isbn, args.member, date.today())
        print("due", loan.due)


if __name__ == "__main__":
    main()
''',
"web/api.js": '''import { cached } from './cache.js';

const BASE = '/api';

export async function getJson(path, { ttl = 30000 } = {}) {
  return cached(path, ttl, async () => {
    const response = await fetch(BASE + path);
    if (!response.ok) throw new Error(`Request failed: ${response.status}`);
    return response.json();
  });
}

export async function checkout(isbn, member) {
  const response = await fetch(`${BASE}/loans`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ isbn, member }),
  });
  if (response.status === 409) return { ok: false, reason: 'unavailable' };
  if (!response.ok) throw new Error('Checkout failed');
  return { ok: true, loan: await response.json() };
}

export function searchBooks(query) {
  return getJson(`/search?q=${encodeURIComponent(query)}`, { ttl: 5000 });
}
''',
"web/cache.js": '''const entries = new Map();

export async function cached(key, ttl, load) {
  const hit = entries.get(key);
  const now = Date.now();
  if (hit && hit.expires > now) return hit.value;
  const pending = hit && hit.pending;
  if (pending) return pending;
  const promise = load().then(value => {
    entries.set(key, { value, expires: Date.now() + ttl });
    return value;
  }, error => {
    entries.delete(key);
    throw error;
  });
  entries.set(key, { pending: promise, expires: 0 });
  return promise;
}

export function clearCache() {
  entries.clear();
}
''',
"README.md": '''# Shelfmark

A tiny library catalog and loan tracker used to demo Blindspot.

## Run

    python cli.py find "pragmatic"

## Rules

Loans last 21 days and can be renewed twice. Late fees start after a 3 day grace period.
''',
}

# Which lines each file has had on screen (None = never opened).
SEEN = {
    "catalog.py": [(1, 999)],
    "loans.py": [(1, 31), (40, 48)],
    "fines.py": [(1, 15)],
    "search.py": [(1, 12)],
    "cli.py": [(1, 12), (28, 33)],
    "web/api.js": [(1, 10)],
    "web/cache.js": None,
    "notifications.py": None,
    "README.md": [(1, 999)],
}
# (days ago, files viewed that day)
SESSIONS = [(19, ["catalog.py", "loans.py"]), (12, ["loans.py", "fines.py", "search.py"]), (5, ["cli.py", "web/api.js", "README.md"]), (1, ["fines.py", "catalog.py"])]
COMMITS = [(34, ["catalog.py", "loans.py", "README.md"], "Add catalog and loan ledger"),
           (26, ["fines.py", "search.py", "cli.py"], "Add fines, search and a CLI"),
           (14, ["notifications.py", "web/api.js", "web/cache.js"], "Add reminders and the web client"),
           (6, ["loans.py", "fines.py"], "Cap renewals and fine total"),
           (2, ["web/cache.js", "search.py"], "Dedupe in-flight requests; weight titles over authors")]

QUESTIONS = [
    ("A book is returned 4 days late. What fine does fine_for compute?", ["0 cents", "25 cents", "100 cents", "1500 cents"], 2,
     "Past the 3 day grace period every late day counts, so 4 * 25 = 100.", "Lines 16-19 apply the grace check, then charge for all late days."),
    ("What does the CAP_CENTS constant do?", ["Limits a single fine to 1500 cents", "Limits a member's total balance", "Sets the daily rate", "Caps how many days can be late"], 0,
     "min(CAP_CENTS, ...) bounds each fine.", "Line 19 takes the minimum of the cap and the computed amount."),
    ("When does apply_waiver forgive a balance?", ["Always for good standing members", "When the balance is at most 100 cents and the member is in good standing",
                                                    "When the balance is over 100 cents", "Never"], 1,
     "Both conditions must hold.", "Lines 22-24 check the standing flag and the balance threshold together."),
]
ANSWERS = [(2, "solid"), (1, "solid"), (1, "shaky")]  # the second is wrong with solid confidence


def git(root: Path, *args, when=None):
    env = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}
    if when: env.update(GIT_AUTHOR_DATE=when, GIT_COMMITTER_DATE=when)
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, env=env)


# Later commits change these lines; earlier commits carry the old text.
EDITS = {3: [("loans.py", "MAX_RENEWALS = 2", "MAX_RENEWALS = 3"), ("fines.py", "CAP_CENTS = 1500", "CAP_CENTS = 2500")],
         4: [("web/cache.js", "  const pending = hit && hit.pending;\n  if (pending) return pending;\n", ""), ("search.py", "3.0 * title[t]", "2.0 * title[t]")]}


def content_at(name: str, index: int) -> str:
    text = FILES[name]
    for later, edits in EDITS.items():
        if later > index:
            for edited, new, old in edits:
                if edited == name: text = text.replace(new, old)
    return text


def build_project(root: Path, now: datetime):
    root.mkdir(parents=True)
    git(root, "init", "-b", "main"); git(root, "config", "user.name", "Demo Author"); git(root, "config", "user.email", "demo@example.test")
    for index, (days, names, message) in enumerate(COMMITS):
        for name in names:
            (root / name).parent.mkdir(parents=True, exist_ok=True)
            (root / name).write_text(content_at(name, index))
        git(root, "add", "-A")
        git(root, "commit", "-m", message, when=(now - timedelta(days=days)).isoformat())


def record(store: SQLiteStore, root: Path, now: datetime):
    for days, names in SESSIONS:
        sid = str(uuid.uuid4()); day = now - timedelta(days=days); sequence = 0; clock = 0
        def event(kind, payload, ms=0):
            nonlocal sequence
            value = {"schema_version": 1, "workspace": str(root), "session_id": sid, "sequence": sequence,
                     "observed_at": (day + timedelta(seconds=sequence)).isoformat(), "monotonic_ms": ms, "kind": kind, "payload": payload}
            sequence += 1
            return value
        store.append(event("session_start", {"mode": "visible-editors-reported-ranges", "heartbeat_interval_ms": 2000}))
        for name in names:
            text = FILES[name]
            store.append(event("snapshot", {"path": name, "text": text, "content_hash": digest(text), "line_count": len(text.split("\n")), "origin": "document"}, clock))
            real = len(text.split("\n"))  # the dashboard counts the empty line after the final newline
            for start, end in [(a, min(b, real)) for a, b in SEEN.get(name) or [] if a <= real]:
                clock += 1000
                store.append(event("visibility", {"path": name, "content_hash": digest(text), "ranges": [[start, end]], "start_ms": clock - 1000, "end_ms": clock,
                    "duration_ms": 1000, "focused": True, "focus_scope": "window", "editor_focus": "unverified", "pane_id": "main",
                    "active": True, "exposure": "reported-visible"}, clock))
            store.append(event("interaction", {"path": name, "kind": "selection", "cause": "keyboard-event"}, clock))


def add_quiz(dashboard: Dashboard, root: Path, now: datetime):
    manifest = export_target(root / "fines.py", 1, 32, name="late-fees")
    questions = [{"prompt": p, "options": o, "correct_index": c, "explanation": e,
                  "rationale": {"path": "fines.py", "start_line": 1, "end_line": 32, "reason": r}} for p, o, c, e, r in QUESTIONS]
    set_id = dashboard.reviews.import_quiz({"schema_version": 1, "generator": "demo fixture", "manifest": manifest, "questions": questions}, now)["set_id"]
    attempt = dashboard.review_post("start", {"set_id": set_id})["attempt_id"]
    for number, (choice, confidence) in enumerate(ANSWERS, 1):
        dashboard.review_post("answer", {"attempt_id": attempt, "question_id": f"q{number}", "chosen_index": choice, "confidence": confidence})
    dashboard.review_post("complete", {"attempt_id": attempt})


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=Path("sandbox/demo"))
    parser.add_argument("--force", action="store_true", help="replace an existing demo")
    args = parser.parse_args()
    out = args.out.resolve()
    if out.exists():
        if not args.force: sys.exit(f"{out} exists. Use --force to rebuild it.")
        shutil.rmtree(out)
    now = datetime.now(timezone.utc)
    project = out / "project"
    build_project(project, now)
    store = SQLiteStore(out / "state", project.resolve())
    try:
        record(store, project.resolve(), now)
        add_quiz(Dashboard(store, out / "state"), project.resolve(), now)
    finally:
        store.close()
    print(f"Demo ready in {out}\nServe it with:\n  .venv/bin/python -B -m blindspot observer serve --workspace {out}/project --state-dir {out}/state --port 7777")


if __name__ == "__main__":
    main()
