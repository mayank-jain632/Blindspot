from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import sys

from .adapters.claude_code import discover, source_key
from .models import timestamp
from .scan.repo import DEFAULT_EXCLUSIONS, RepoError, Repository
from .scan.report import build_report, encode, render, safe
from .state import State, StateError
from .review.cli import add_commands, run as run_review


def parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--state-dir", type=Path, default=argparse.SUPPRESS)
    common.add_argument("--sessions-dir", type=Path, default=argparse.SUPPRESS)
    common.add_argument("--json", action="store_true", default=argparse.SUPPRESS)
    common.add_argument("--read-only", action="store_true", default=argparse.SUPPRESS,
                        help="read existing configuration without saving application state")
    common.add_argument("--source-root", action="append", type=Path, default=argparse.SUPPRESS,
                        help="temporarily map transcripts starting in this recorded cwd to the inspected checkout")
    common.add_argument("--now", default=argparse.SUPPRESS, help="fixed timezone-aware ISO timestamp")
    common.add_argument("--grace-hours", type=float, default=argparse.SUPPRESS)
    common.add_argument("--exclude", action="append", default=argparse.SUPPRESS)
    common.add_argument("--include", action="append", default=argparse.SUPPRESS)
    common.add_argument("--no-default-exclusions", action="store_true", default=argparse.SUPPRESS)
    root = argparse.ArgumentParser(prog="blindspot", parents=[common],
        description="Local evidence about recorded agent activity; not authorship or comprehension.")
    commands = root.add_subparsers(dest="command", required=True)
    for name in ("scan", "doctor"):
        command = commands.add_parser(name, parents=[common])
        command.add_argument("path", type=Path, nargs="?", default=Path.cwd())
    brief = commands.add_parser("brief", parents=[common])
    brief.add_argument("file", type=Path)
    identity = commands.add_parser("identity", parents=[common])
    identity.add_argument("path", type=Path, nargs="?", default=Path.cwd())
    identity.add_argument("--confirm", action="append", default=[])
    identity.add_argument("--remove", action="append", default=[])
    link = commands.add_parser("link", parents=[common])
    link.add_argument("source")
    link.add_argument("path", type=Path)
    add_commands(commands, common)
    observer = commands.add_parser("observer", help="Local VS Code collector experiment")
    actions = observer.add_subparsers(dest="observer_action", required=True)
    receiver = actions.add_parser("serve")
    receiver.add_argument("--workspace", type=Path, required=True)
    receiver.add_argument("--state-dir", type=Path, required=True)
    receiver.add_argument("--port", type=int, default=7777)
    receiver.add_argument("--review-state-dir", type=Path, help="Existing quiz state directory; defaults to observer state")
    overview = actions.add_parser("overview")
    overview.add_argument("--workspace", type=Path, required=True)
    overview.add_argument("--state-dir", type=Path, required=True)
    overview.add_argument("--dwell-ms", type=float, default=1000)
    report = actions.add_parser("report")
    report.add_argument("--workspace", type=Path, required=True)
    report.add_argument("--state-dir", type=Path, required=True)
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "observer":
            if getattr(args, "read_only", False):
                raise ValueError("Observer commands use their own experimental journal; --read-only is not supported")
            from .observer.store import Journal
            if args.observer_action == "serve":
                from .observer.server import serve
                if not 0 <= args.port <= 65535:
                    raise ValueError("Port must be between 0 and 65535")
                serve(args.state_dir, args.workspace, args.port, args.review_state_dir)
            else:
                # Report should never initialize a missing journal directory.
                from .observer.sqlite_store import SQLiteStore
                if (args.state_dir.expanduser() / "observations.sqlite3").is_file():
                    store = SQLiteStore(args.state_dir, args.workspace, read_only=True)
                    try: print(json.dumps(store.overview(args.dwell_ms) if args.observer_action == "overview" else store.report(), indent=2))
                    finally: store.close()
                elif args.observer_action == "report" and (args.state_dir.expanduser() / "events.jsonl").is_file():
                    print(json.dumps(Journal(args.state_dir, args.workspace).report(), indent=2))
                else:
                    raise ValueError("No observer journal exists at this state directory")
            return 0
        read_only = getattr(args, "read_only", False)
        source_roots = getattr(args, "source_root", [])
        if read_only and (args.command == "link" or args.command == "identity" and (args.confirm or args.remove)):
            raise ValueError("--read-only cannot save links or change identities.")
        if source_roots and args.command not in {"scan", "doctor", "brief"}:
            raise ValueError("--source-root is available only for scan, doctor, and brief.")
        state = State(getattr(args, "state_dir", Path.home() / ".blindspot"), read_only=read_only)
        sessions = getattr(args, "sessions_dir", Path.home() / ".claude" / "projects").expanduser()
        grace = getattr(args, "grace_hours", 24.0)
        if not math.isfinite(grace) or grace < 0 or grace > 24 * 365:
            raise ValueError("Grace must be finite and between 0 and 8760 hours.")
        now_raw = getattr(args, "now", None)
        now = timestamp(now_raw) if now_raw is not None else datetime.now(timezone.utc)
        if now is None:
            raise ValueError("--now requires an ISO timestamp with a timezone.")
        if args.command in {"target", "quiz"}:
            return run_review(args, state.directory, now, read_only)
        if args.command == "link":
            repo = Repository(args.path)
            state.guard_repository(repo.root)
            paths, _ = discover(sessions)
            requested_source = str(Path(args.source).expanduser().resolve())
            matches = [p for p in paths if args.source in {str(p), str(p.resolve()), source_key(p)}
                       or requested_source == str(p.resolve())]
            if len(matches) != 1:
                raise ValueError("Source must identify exactly one discovered main transcript by path or source key.")
            state.data["links"][source_key(matches[0])] = {"root": str(repo.root), "source": str(matches[0].resolve())}
            state.save()
            print(f"Linked {source_key(matches[0])} to {safe(repo.root)} explicitly.")
            return 0
        if args.command == "identity":
            repo = Repository(args.path)
            state.guard_repository(repo.root)
            record = state.checkout(str(repo.root), repo.key)
            identities = set(record.get("identities", []))
            use_configured = record.get("use_configured_identity", True)
            if repo.email and use_configured:
                identities.add(repo.email)
            for email in args.confirm:
                if "@" not in email or any(c in email for c in "\r\n<>"):
                    raise ValueError("Confirm a valid Git email identity.")
                identities.add(repo.canonical_email(email))
                if repo.canonical_email(email) == repo.email:
                    use_configured = True
            identities.difference_update(repo.canonical_email(e) for e in args.remove)
            if repo.email in {repo.canonical_email(e) for e in args.remove}:
                use_configured = False
            state.data["checkouts"][str(repo.root)] = {**record, "repository_key": repo.key,
                "identities": sorted(identities), "use_configured_identity": use_configured}
            state.save()
            authors = repo.history({})
            output = {"checkout": str(repo.root), "confirmed": sorted(identities),
                "historical_authors": [{"email": email, "name": name, "confirmed": email in identities}
                    for email, name in authors.items()]}
            print(json.dumps(output, indent=2, ensure_ascii=True))
            return 0
        selected = args.file.expanduser().absolute() if args.command == "brief" else args.path.expanduser()
        if args.command == "brief":
            selected = selected.parent.resolve() / selected.name
        path = selected.parent if args.command == "brief" else selected
        if args.command == "brief":
            # A committed path can be deleted in the working tree, including
            # its parent directory. Resolve the checkout from a surviving ancestor.
            while not path.exists() and path != path.parent:
                path = path.parent
        exclusions = ([] if getattr(args, "no_default_exclusions", False) else DEFAULT_EXCLUSIONS) + getattr(args, "exclude", [])
        report = build_report(path, sessions, state, now, grace, exclusions,
                              getattr(args, "include", []), source_roots=source_roots)
        if args.command == "brief":
            relative = os.path.relpath(selected, report["checkout"])
            file = next((f for f in report["files"] if f["path"] == relative), None)
            if file is None:
                raise ValueError("This path is not an eligible text file at the captured HEAD.")
            output = {"checkout": report["checkout"], "head": report["head"],
                "analysis_status": report["analysis_status"], "read_only": report["read_only"],
                "temporary_source_links": report["temporary_source_links"],
                "policy": report["policy"], "file": file}
            print(json.dumps(output, indent=2, default=encode, ensure_ascii=True))
        elif getattr(args, "json", False):
            print(json.dumps(report, indent=2, default=encode, ensure_ascii=True))
        else:
            print(render(report, doctor=args.command == "doctor"))
        return 0
    except (RepoError, StateError, ValueError) as error:
        print(f"blindspot: {safe(error)}", file=sys.stderr)
        return 2
    except (KeyboardInterrupt, EOFError):
        print("Review paused; submitted answers are preserved.", file=sys.stderr)
        return 130
    except OSError:
        print("blindspot: A local file or command could not be accessed.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
