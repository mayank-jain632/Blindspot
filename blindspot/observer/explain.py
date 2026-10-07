"""Optional plain-English explanations from a model running on this machine.

Only a loopback Ollama endpoint is accepted, so source never leaves the
computer. The model receives one code unit (or a file outline), never the
repository, and its text is shown as generated, unverified output."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import socket
import threading
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

DEFAULT_URL = "http://127.0.0.1:11434"
PROMPT_VERSION = 1
MAX_CODE_LINES = 200
MAX_CODE_CHARS = 12000
MAX_REPLY_CHARS = 3000
MAX_CACHED = 500
LOOPBACK = {"localhost", "127.0.0.1", "::1"}
MODEL_NAME = re.compile(r"^[\w.:/@-]{1,100}$")

SYSTEM = ("You help a developer review code they have not read. You only know what is in the text you are given. "
          "Be concise and concrete, and say so when something cannot be determined from it. Never invent behavior.")
UNIT_TASK = ("Explain this code in plain English for someone who has not read it. Use at most 6 short bullet points. "
             "Spend most of them on the lines listed as never on screen, saying what those lines do and why they matter. "
             "Refer to lines like (L25). If the snippet alone does not make something clear, say that instead of guessing.")
FILE_TASK = ("Using only this outline, write 4 to 6 sentences: what the file is for, how its parts fit together, and which parts "
             "that were never on screen are most worth reading first. Do not describe code you have not been shown.")


class LLMError(Exception):
    """A problem with the local model that is safe to show the user."""


def loopback_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or parsed.hostname not in LOOPBACK or parsed.username or parsed.password:
        raise ValueError("The local model endpoint must be on this machine (localhost or 127.0.0.1)")
    return url.rstrip("/")


def valid_model(name) -> str:
    if not isinstance(name, str) or not MODEL_NAME.fullmatch(name): raise LLMError("Choose an installed model first.")
    return name


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, newurl):
        raise HTTPError(request.full_url, code, "Local model redirects are disabled", headers, fp)


class Ollama:
    def __init__(self, url: str = DEFAULT_URL, model: str | None = None, timeout: float = 180):
        self.url = loopback_url(url)
        self.default_model = model
        self.timeout = timeout
        # No environment proxy: this call must go straight to localhost.
        self.opener = build_opener(ProxyHandler({}), NoRedirects())

    def _request(self, path, body=None, timeout=None):
        request = Request(self.url + path, data=None if body is None else json.dumps(body).encode(),
                          headers={"Content-Type": "application/json"}, method="GET" if body is None else "POST")
        return json.loads(self.opener.open(request, timeout=timeout or self.timeout).read(8 * 1024 * 1024))

    def status(self) -> dict:
        try:
            names = [m["name"] for m in self._request("/api/tags", timeout=2).get("models", []) if isinstance(m, dict) and "name" in m]
        except (URLError, OSError, ValueError, KeyError):
            return {"available": False, "endpoint": self.url, "models": [], "default": None,
                    "error": "Ollama is not running. Start it (the Ollama app, or `ollama serve`) and refresh."}
        names = [n for n in names if "embed" not in n.lower()]
        default = (self.default_model if self.default_model in names else
                   next((n for n in names if "coder" in n.lower()), names[0] if names else None))
        error = None if names else "Ollama is running but has no models. Install one, for example `ollama pull qwen2.5-coder:7b`."
        return {"available": bool(names), "endpoint": self.url, "models": names, "default": default, "error": error}

    def chat(self, model: str, system: str, user: str) -> str:
        valid_model(model)
        body = {"model": model, "stream": False, "options": {"temperature": 0.2, "num_predict": 500},
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        try:
            data = self._request("/api/chat", body)
        except HTTPError as exc:
            if exc.code == 404: raise LLMError(f"Model {model} is not installed. Run: ollama pull {model}") from None
            raise LLMError(f"Ollama returned an error ({exc.code}).") from None
        except (socket.timeout, TimeoutError):
            raise LLMError(f"The model took longer than {int(self.timeout)} seconds. Try a smaller model or a shorter unit.") from None
        except URLError as exc:
            if isinstance(exc.reason, (socket.timeout, TimeoutError)):
                raise LLMError(f"The model took longer than {int(self.timeout)} seconds. Try a smaller model or a shorter unit.") from None
            raise LLMError("Ollama is not running. Start it and try again.") from None
        except (OSError, ValueError):
            raise LLMError("Could not read Ollama's reply.") from None
        content = data.get("message", {}).get("content") if isinstance(data, dict) else None
        text = re.sub(r"<think>.*?</think>", "", content or "", flags=re.S).strip()
        if not text: raise LLMError("The model returned nothing. Try again or choose another model.")
        return text[:MAX_REPLY_CHARS]


# ---- prompts (pure) -------------------------------------------------------

def _numbered(lines, ranges):
    out = []; chars = 0; truncated = False
    for index, (start, end) in enumerate(ranges):
        if index: out.append("   ...")
        for number in range(start, end + 1):
            row = f"{number:>5}| {lines[number - 1]}"
            if len(out) >= MAX_CODE_LINES or chars + len(row) > MAX_CODE_CHARS: truncated = True; break
            out.append(row); chars += len(row) + 1
        if truncated: break
    if truncated: out.append("   ... (truncated)")
    return "\n".join(out)


def _spans(ranges):
    return ", ".join(f"{a}" if a == b else f"{a}-{b}" for a, b in ranges)


def unit_prompt(path, item, lines):
    parts = [f"File: {path}", f"Unit: {item['kind']} {item['name']} (lines {item['start']}-{item['end']})"]
    if item.get("signature") and item["kind"] != "block": parts.append(f"Signature: {item['signature']}")
    if item.get("doc"): parts.append(f"Docstring: {item['doc']}")
    parts.append(f"Never on screen: {_spans(item['unseen_ranges'])} ({item['unseen']} of {item['lines']} lines)" if item["unseen"]
                 else "Never on screen: nothing (every line has been on screen)")
    if item.get("calls"): parts.append("Calls: " + ", ".join(item["calls"]))
    if item.get("raises"): parts.append("Raises: " + ", ".join(item["raises"]))
    if item.get("changes"):
        change = item["changes"][0]
        parts.append(f"Last changed: {change['date'] or 'not committed yet'}, \"{change['summary']}\"")
    parts += ["", "Code:", _numbered(lines, item.get("ranges") or [[item["start"], item["end"]]]), "", UNIT_TASK]
    return "\n".join(parts)


def file_prompt(guide):
    parts = [f"File: {guide['path']}", f"{guide['unseen_lines']} of {guide['line_count']} lines were never on screen."]
    if guide["overview"].get("doc"): parts.append(f"Module docstring: {guide['overview']['doc']}")
    if guide["overview"].get("imports"): parts.append("Uses: " + ", ".join(guide["overview"]["imports"]))
    parts += ["", "Code units:"]
    for item in guide["items"][:60]:
        line = f"- {item['kind']} {item['name']} (lines {item['start']}-{item['end']}): {item['unseen']} of {item['lines']} lines never on screen"
        if item.get("doc"): line += f". {item['doc']}"
        parts.append(line)
    parts += ["", FILE_TASK]
    return "\n".join(parts)


# ---- cache ----------------------------------------------------------------

class ExplanationCache:
    """Generated text keyed by file content, unit and model; stored beside observer state."""
    def __init__(self, directory: Path):
        self.path = Path(directory) / "explanations.json"
        self.lock = threading.Lock()

    @staticmethod
    def key(model, path, content_hash, start, end, prompt):
        return hashlib.sha256(json.dumps([PROMPT_VERSION, SYSTEM, model, path, content_hash, start, end, prompt]).encode()).hexdigest()

    def _read(self):
        try: data = json.loads(self.path.read_text())
        except (OSError, ValueError): return {}
        return data if isinstance(data, dict) else {}

    def get(self, key):
        with self.lock: return self._read().get(key)

    def put(self, key, value):
        with self.lock:
            data = self._read(); data[key] = value
            for old in sorted(data, key=lambda k: data[k].get("generated_at", ""))[:max(0, len(data) - MAX_CACHED)]: del data[old]
            temp = self.path.with_suffix(".tmp")
            fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w") as handle: json.dump(data, handle)
            temp.replace(self.path)
