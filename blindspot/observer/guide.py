"""Study guide for one file: its code units, which lines were never on screen,
and what last changed them. Built from structure (AST / patterns) and Git
blame only. No model is involved, so nothing here can be invented."""
from __future__ import annotations

import ast
import builtins
from datetime import datetime, timedelta, timezone
import os
import re
import subprocess

MAX_ITEMS = 150
RECENT_DAYS = 90
NOISE_CALLS = set(dir(builtins))
CLOSERS = ("}", ")", "]", "end")
NON_METHODS = {"if", "for", "while", "switch", "catch", "return", "else", "function", "constructor_", "with", "do", "try"}
MODS = r"(?:(?:public|private|protected|internal|static|final|abstract|override|virtual|async|suspend|synchronized|open|sealed|partial|readonly|export|default|unsafe|pub(?:\([^)]*\))?)\s+)"


def _rx(pattern, flags=0):
    return re.compile(pattern, flags)


# kind, regex, name group. Order matters: first match wins for a line.
JS = [("function", _rx(r"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s*\*?\s*([A-Za-z_$][\w$]*)"), 1),
      ("class", _rx(r"^\s*(?:export\s+)?(?:default\s+)?(?:abstract\s+)?class\s+([A-Za-z_$][\w$]*)"), 1),
      ("type", _rx(r"^\s*(?:export\s+)?(?:declare\s+)?(?:interface|type|enum)\s+([A-Za-z_$][\w$]*)"), 1),
      ("function", _rx(r"^\s*(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*(?::[^=]+)?=\s*(?:async\s*)?(?:function\b|\([^)]*\)\s*(?::[^=]+)?=>|[A-Za-z_$][\w$]*\s*=>)"), 1),
      ("method", _rx(r"^\s+(?:(?:public|private|protected|static|async|readonly|override|get|set)\s+)*([A-Za-z_$][\w$]*)\s*\([^;]*\)\s*(?::\s*[^{=]+)?\{\s*$"), 1)]
GO = [("function", _rx(r"^func\s+(?:\([^)]*\)\s*)?(\w+)"), 1),
      ("type", _rx(r"^type\s+(\w+)\s+(?:struct|interface)"), 1)]
RUST = [("function", _rx(r"^\s*(?:pub(?:\([^)]*\))?\s+)?(?:const\s+)?(?:async\s+)?(?:unsafe\s+)?fn\s+(\w+)"), 1),
        ("type", _rx(r"^\s*(?:pub(?:\([^)]*\))?\s+)?(?:struct|enum|trait|union)\s+(\w+)"), 1),
        ("class", _rx(r"^\s*(?:unsafe\s+)?impl\b(?:<[^>]*>)?\s*([^{]+?)\s*(?:\{|where\b|$)"), 1)]
JVM = [("class", _rx(rf"^\s*{MODS}*(?:class|interface|enum|record|object|trait|struct)\s+(\w+)"), 1),
       ("function", _rx(r"^\s*(?:(?:public|private|protected|internal|override|open|suspend|inline)\s+)*fun\s+(?:<[^>]*>\s*)?(?:[\w.]+\.)?(\w+)"), 1),
       ("function", _rx(r"^\s*(?:(?:public|private|protected|internal|static|final|override|open)\s+)*func\s+(\w+)"), 1),
       ("method", _rx(rf"^\s*{MODS}+[\w<>\[\],.?\s]*?\b(\w+)\s*\([^;]*$"), 1)]
PHP = [("class", _rx(r"^\s*(?:abstract\s+|final\s+)?(?:class|interface|trait)\s+(\w+)"), 1),
       ("function", _rx(r"^\s*(?:(?:public|private|protected|static|abstract|final)\s+)*function\s+&?(\w+)"), 1)]
CLIKE = [("class", _rx(r"^\s*(?:class|struct|enum|namespace)\s+(\w+)"), 1),
         ("function", _rx(r"^[A-Za-z_][\w:<>,*&\s]*?[\s*&](\w+)\s*\([^;]*\)\s*(?:const\s*)?\{?\s*$"), 1)]
RUBY = [("class", _rx(r"^\s*(?:class|module)\s+([\w:]+)"), 1),
        ("function", _rx(r"^\s*def\s+(?:self\.)?(\w+[?!=]?)"), 1)]
SHELL = [("function", _rx(r"^\s*(?:function\s+)?([\w-]+)\s*\(\)\s*\{"), 1)]
SQL = [("type", _rx(r"^\s*create\s+(?:or\s+replace\s+)?(?:unique\s+)?(?:table|view|function|procedure|index)\s+(?:if\s+not\s+exists\s+)?([\w.\"]+)", re.I), 1)]
PYTHON_FALLBACK = [("class", _rx(r"^\s*class\s+(\w+)"), 1), ("function", _rx(r"^\s*(?:async\s+)?def\s+(\w+)"), 1)]
BY_EXTENSION = {
    "js": JS, "jsx": JS, "ts": JS, "tsx": JS, "mjs": JS, "cjs": JS, "svelte": JS, "vue": JS,
    "go": GO, "rs": RUST, "java": JVM, "kt": JVM, "kts": JVM, "scala": JVM, "cs": JVM, "swift": JVM,
    "php": PHP, "c": CLIKE, "h": CLIKE, "cpp": CLIKE, "hpp": CLIKE, "cc": CLIKE,
    "rb": RUBY, "sh": SHELL, "bash": SHELL, "zsh": SHELL, "sql": SQL,
}
IMPORT_JS = _rx(r"""(?:from\s+|require\()\s*['"]([^'"]+)['"]""")


def _indent(line):
    expanded = line.expandtabs(4)
    return len(expanded) - len(expanded.lstrip())


def _trim(lines, start, end):
    while end > start and not lines[end - 1].strip(): end -= 1
    return end


def _ranges_minus(span, holes):
    """Lines of span (inclusive) not covered by the sorted hole spans."""
    start, end = span; result = []; cursor = start
    for h_start, h_end in sorted(holes):
        if h_start > cursor: result.append([cursor, h_start - 1])
        cursor = max(cursor, h_end + 1)
    if cursor <= end: result.append([cursor, end])
    return result


def _count(ranges):
    return sum(e - s + 1 for s, e in ranges)


def _clip_blank_edges(lines, ranges):
    """Drop blank lines at the edges of each range so gaps do not read as code."""
    result = []
    for start, end in ranges:
        while start <= end and not lines[start - 1].strip(): start += 1
        while end >= start and not lines[end - 1].strip(): end -= 1
        if start <= end: result.append([start, end])
    return result


# ---- structure extraction -------------------------------------------------

def _py_calls(node):
    seen = []
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            try: name = ast.unparse(child.func)
            except Exception: continue
            if len(name) > 40 or not re.fullmatch(r"[\w.]+", name): continue
            if name.split(".")[0] in NOISE_CALLS and "." not in name: continue
            if name not in seen: seen.append(name)
    return seen[:8]


def _py_raises(node):
    seen = []
    for child in ast.walk(node):
        if isinstance(child, ast.Raise) and child.exc is not None:
            target = child.exc.func if isinstance(child.exc, ast.Call) else child.exc
            try: name = ast.unparse(target)
            except Exception: continue
            if len(name) <= 40 and name not in seen: seen.append(name)
    return seen[:4]


BRANCHES = (ast.If, ast.For, ast.AsyncFor, ast.While, ast.Try, ast.ExceptHandler, ast.BoolOp, ast.IfExp, ast.comprehension)


def _py_items(text):
    try: tree = ast.parse(text)
    except (SyntaxError, ValueError, RecursionError, MemoryError): return None
    items = []
    def visit(body, prefix=""):
        for node in body:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)): continue
            start = min([node.lineno, *(d.lineno for d in node.decorator_list)])
            name = prefix + node.name
            doc = (ast.get_docstring(node) or "").strip().split("\n\n")[0].replace("\n", " ")
            if isinstance(node, ast.ClassDef):
                bases = ", ".join(ast.unparse(b) for b in node.bases)
                item = {"kind": "class", "signature": f"class {node.name}" + (f"({bases})" if bases else "")}
            else:
                try: args = ast.unparse(node.args)
                except Exception: args = "..."
                returns = ""
                if node.returns is not None:
                    try: returns = " -> " + ast.unparse(node.returns)
                    except Exception: pass
                kind = "method" if prefix else "function"
                item = {"kind": kind, "signature": ("async " if isinstance(node, ast.AsyncFunctionDef) else "") + f"def {node.name}({args}){returns}",
                        "calls": _py_calls(node), "raises": _py_raises(node),
                        "branches": sum(isinstance(c, BRANCHES) for c in ast.walk(node))}
            item.update(name=name, start=start, end=node.end_lineno, doc=doc[:240],
                        decorators=[ast.unparse(d)[:40] for d in node.decorator_list][:3])
            items.append(item)
            if isinstance(node, ast.ClassDef): visit(node.body, name + ".")
    visit(tree.body)
    module_doc = (ast.get_docstring(tree) or "").strip().split("\n\n")[0].replace("\n", " ")[:240]
    imports = []
    for node in tree.body:
        if isinstance(node, ast.Import): names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            dots = "." * node.level
            names = [dots + node.module] if node.module else [dots + a.name for a in node.names]
        else: names = []
        for n in names:
            if n not in imports: imports.append(n)
    return items, module_doc, imports[:12]


def _pattern_items(lines, patterns):
    starts = []
    for number, line in enumerate(lines, 1):
        stripped = line.strip()
        if not stripped: continue
        for kind, regex, group in patterns:
            match = regex.match(line)
            if not match: continue
            name = re.sub(r"\s+", " ", match.group(group)).strip()
            if kind == "method" and (name in NON_METHODS or _indent(line) == 0): continue
            starts.append((number, kind, name[:80], _indent(line), stripped[:140]))
            break
    items = []
    for number, kind, name, indent, signature in starts:
        end = number
        for i in range(number + 1, len(lines) + 1):
            line = lines[i - 1]
            if not line.strip(): continue
            if _indent(line) <= indent:
                end = i if line.strip().startswith(CLOSERS) else i - 1
                break
            end = i
        end = max(number, _trim(lines, number, end))
        items.append({"kind": kind, "name": name, "start": number, "end": end, "signature": signature, "doc": ""})
    return items


def _markdown_items(lines):
    heads = []; fenced = False
    for number, line in enumerate(lines, 1):
        if line.lstrip().startswith(("```", "~~~")): fenced = not fenced
        match = None if fenced else re.match(r"^(#{1,4})\s+(.+?)\s*#*\s*$", line)
        if match: heads.append((number, len(match.group(1)), match.group(2)[:80]))
    items = []
    for i, (number, level, title) in enumerate(heads):
        end = len(lines)
        for next_number, next_level, _ in heads[i + 1:]:
            if next_level <= level: end = next_number - 1; break
        items.append({"kind": "section", "name": title, "start": number, "end": max(number, _trim(lines, number, end)), "signature": "#" * level + " " + title, "doc": ""})
    return items


def _block_items(lines):
    items = []; start = None
    for number, line in enumerate(lines + [""], 1):
        if line.strip() and start is None: start = number
        elif not line.strip() and start is not None:
            first = lines[start - 1].strip()
            for chunk in range(start, number, 40):  # long unbroken runs become 40-line pieces
                head = lines[chunk - 1].strip()
                items.append({"kind": "block", "name": head[:60], "start": chunk, "end": min(number - 1, chunk + 39), "signature": head[:140], "doc": ""})
            start = None
    return items


def _imports_pattern(text, extension):
    if extension not in {"js", "jsx", "ts", "tsx", "mjs", "cjs", "svelte", "vue"}: return []
    found = []
    for name in IMPORT_JS.findall(text):
        if name not in found: found.append(name)
    return found[:12]


def extract(text, path):
    """Return (items, module_doc, imports, parser) for a file's text."""
    lines = text.split("\n")
    if lines and lines[-1] == "": lines = lines[:-1]
    extension = path.rsplit(".", 1)[-1].lower() if "." in path.rsplit("/", 1)[-1] else ""
    if extension == "py":
        parsed = _py_items(text)
        if parsed and parsed[0]: return parsed[0], parsed[1], parsed[2], "python-ast", lines
        if parsed: return _block_items(lines), parsed[1], parsed[2], "blocks", lines
        return _pattern_items(lines, PYTHON_FALLBACK), "", [], "patterns", lines
    if extension in {"md", "markdown"}:
        items = _markdown_items(lines)
        if items: return items, "", [], "headings", lines
    elif extension in BY_EXTENSION:
        items = _pattern_items(lines, BY_EXTENSION[extension])
        if items: return items, "", _imports_pattern(text, extension), "patterns", lines
    return _block_items(lines), "", [], "blocks", lines


# ---- Git blame ------------------------------------------------------------

def blame(workspace, path, line_count, timeout=5):
    """Last-touching commit per current line, or None if history is unavailable."""
    env = {**os.environ, "GIT_OPTIONAL_LOCKS": "0"}
    try:
        result = subprocess.run(["git", "-C", str(workspace), "blame", "--porcelain", "-w", "--", path],
                                capture_output=True, env=env, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired): return None
    if result.returncode != 0 or len(result.stdout) > 8 * 1024 * 1024: return None
    commits = {}; per_line = {}; current = None; final = None
    for raw in result.stdout.decode("utf-8", "replace").split("\n"):
        if raw.startswith("\t"):
            if current is not None and final is not None: per_line[final] = current
            continue
        head = raw.split(" ")
        if len(head) >= 3 and re.fullmatch(r"[0-9a-f]{40}", head[0]) and head[2].isdigit():
            current, final = head[0], int(head[2]); commits.setdefault(current, {"summary": "", "time": None})
        elif current and raw.startswith("summary "): commits[current]["summary"] = raw[8:][:120]
        elif current and raw.startswith("author-time ") and raw[12:].isdigit(): commits[current]["time"] = int(raw[12:])
    if not per_line or max(per_line) > line_count: return None
    for sha, info in commits.items():
        info["uncommitted"] = set(sha) == {"0"}
        info["date"] = None if info["uncommitted"] or info["time"] is None else datetime.fromtimestamp(info["time"], timezone.utc).date().isoformat()
        if info["uncommitted"]: info["summary"] = "Uncommitted changes"
    return {"commits": commits, "lines": per_line}


def _changes(ranges, reported, history, limit):
    """Commits that last touched the given lines, newest first."""
    if not history: return []
    tally = {}
    for start, end in ranges:
        for line in range(start, end + 1):
            sha = history["lines"].get(line)
            if sha is None: continue
            entry = tally.setdefault(sha, {"lines": 0, "unseen": 0})
            entry["lines"] += 1; entry["unseen"] += line not in reported
    rows = []
    for sha, entry in tally.items():
        info = history["commits"][sha]
        rows.append({"commit": sha[:7] if not info["uncommitted"] else None, "date": info["date"], "summary": info["summary"], **entry, "_t": info["time"] or 0, "_u": info["uncommitted"]})
    rows.sort(key=lambda r: (not r["_u"], -r["_t"]))
    for row in rows: row.pop("_t"); row.pop("_u")
    return rows[:limit]


# ---- assembly -------------------------------------------------------------

def build(text, path, reported_ranges, history=None, now=None):
    now = now or datetime.now(timezone.utc)
    raw, module_doc, imports, parser, lines = extract(text, path)
    total = len(lines)
    reported = {n for s, e in reported_ranges for n in range(s, e + 1)}
    raw = [i for i in raw if 1 <= i["start"] <= i["end"] <= total]
    raw.sort(key=lambda i: (i["start"], -i["end"]))
    # Nest by containment so a class owns only its own lines, not its methods'.
    # Helpers declared inside a function body belong to that function, not the guide.
    stack = []; children = {}; kept = []
    for item in raw:
        while stack and not (stack[-1]["start"] <= item["start"] and item["end"] <= stack[-1]["end"]): stack.pop()
        if stack and stack[-1]["kind"] in {"function", "method"}: continue
        item["_top"] = not stack; item["_children"] = []
        if stack: stack[-1]["_children"].append(item)
        stack.append(item); kept.append(item)
    raw = kept
    for item in raw:
        holes = [(c["start"], c["end"]) for c in item["_children"]]
        item["ranges"] = _clip_blank_edges(lines, _ranges_minus((item["start"], item["end"]), holes))
    top = [(i["start"], i["end"]) for i in raw if i["_top"]]
    if raw:
        module_ranges = _clip_blank_edges(lines, _ranges_minus((1, total), top)) if total else []
        if module_ranges:
            raw.append({"kind": "module", "name": "Top-level code", "start": module_ranges[0][0], "end": module_ranges[-1][1],
                        "signature": "", "doc": "", "ranges": module_ranges})
    items = []
    for item in raw[:MAX_ITEMS]:
        own = item["ranges"]
        lines_total = _count(own)
        if not lines_total: continue
        unseen_ranges = []
        for start, end in own:
            run = None
            for n in range(start, end + 1):
                if n in reported:
                    if run: unseen_ranges.append(run); run = None
                elif run: run[1] = n
                else: run = [n, n]
            if run: unseen_ranges.append(run)
        unseen = _count(unseen_ranges)
        recent = _changes(own, reported, history, 3)
        cutoff = (now - timedelta(days=RECENT_DAYS)).date().isoformat()
        items.append({
            "name": item["name"], "kind": item["kind"], "signature": item["signature"], "doc": item.get("doc", ""),
            "start": item["start"], "end": item["end"], "lines": lines_total, "unseen": unseen,
            "state": "seen" if unseen == 0 else "unseen" if unseen == lines_total else "partial",
            "unseen_ranges": unseen_ranges[:8], "ranges": own, "decorators": item.get("decorators", []),
            "calls": item.get("calls", []), "raises": item.get("raises", []), "branches": item.get("branches"),
            "changes": recent, "recently_changed": any((c["date"] and c["date"] >= cutoff) or c["commit"] is None for c in recent),
        })
    items.sort(key=lambda i: (i["start"], -i["end"]))
    whole = [[1, total]] if total else []
    commits = []
    if history:
        for row in _changes(whole, reported, history, 200):
            if row["unseen"]: commits.append(row)
    notes = []
    if len(raw) > MAX_ITEMS: notes.append(f"Showing the first {MAX_ITEMS} code units.")
    if history is None: notes.append("Change history is unavailable for this file (untracked, unsaved edits or no Git).")
    # Same line count as the dashboard (it counts the empty line after a final newline).
    all_lines = len(text.split("\n"))
    unseen_total = sum(1 for n in range(1, all_lines + 1) if n not in reported)
    return {"path": path, "parser": parser, "line_count": all_lines, "unseen_lines": unseen_total,
            "overview": {"doc": module_doc, "imports": imports,
                         "units": len(items), "units_with_unseen": sum(i["unseen"] > 0 for i in items)},
            "items": items, "recent_changes": commits[:8], "notes": notes}
