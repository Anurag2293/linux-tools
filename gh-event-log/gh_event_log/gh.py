from __future__ import annotations

import json
import re
import subprocess


class GhError(Exception):
    """kind: auth | sso | rate_limit | transient | not_found | other"""

    def __init__(self, message: str, kind: str = "other", reset_at: float | None = None):
        super().__init__(message)
        self.kind = kind
        self.reset_at = reset_at


def _classify(text: str) -> str:
    t = text.lower()
    if "saml" in t or "single sign-on" in t:
        return "sso"
    if "http 401" in t or "gh auth login" in t or "authentication" in t or "bad credentials" in t:
        return "auth"
    if "rate limit" in t or "rate_limited" in t:
        return "rate_limit"
    if "http 404" in t or "not_found" in t:
        return "not_found"
    if re.search(r"http 5\d\d", t) or "timeout" in t or "timed out" in t or "connection" in t or "eof" in t:
        return "transient"
    return "other"


def _scrub(text: str) -> str:
    text = re.sub(r"\b(gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})", "<redacted>", text)
    return text.strip()[:500]


class Gh:
    def __init__(self, gh_bin: str = "gh", timeout: int = 90):
        self.gh_bin = gh_bin
        self.timeout = timeout

    def _run(self, args: list, stdin: str | None = None):
        try:
            p = subprocess.run(
                [self.gh_bin] + args,
                input=stdin,
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )
        except subprocess.TimeoutExpired:
            raise GhError(f"gh {args[0]} timed out after {self.timeout}s", "transient")
        except OSError as e:
            raise GhError(f"cannot run gh: {e}", "other")
        return p.returncode, p.stdout, p.stderr

    def auth_ok(self) -> bool:
        rc, _, _ = self._run(["auth", "status", "--hostname", "github.com"])
        return rc == 0

    def rest_get(self, path: str, headers: dict | None = None):
        """Returns (status, headers_lowercased, parsed_body_or_None)."""
        args = ["api", "--include", "--method", "GET", path]
        for k, v in (headers or {}).items():
            args += ["-H", f"{k}: {v}"]
        rc, out, err = self._run(args)
        status, hdrs, body = _parse_included(out)
        if status == 304:
            return status, hdrs, None
        if rc != 0 or status is None or status >= 400:
            msg = _scrub(err or out)
            kind = _classify(msg)
            reset = None
            if status in (403, 429) and hdrs.get("x-ratelimit-remaining") == "0":
                kind = "rate_limit"
                reset = float(hdrs.get("x-ratelimit-reset", 0)) or None
            if "x-github-sso" in hdrs:
                kind = "sso"
            raise GhError(f"GET {path}: {msg}", kind, reset)
        try:
            parsed = json.loads(body) if body.strip() else None
        except ValueError:
            raise GhError(f"GET {path}: invalid JSON", "transient")
        return status, hdrs, parsed

    def graphql(self, query: str, variables: dict | None = None):
        """Returns (data, errors). Raises GhError when there is no usable data."""
        payload = json.dumps({"query": query, "variables": variables or {}})
        rc, out, err = self._run(["api", "graphql", "--input", "-"], stdin=payload)
        try:
            resp = json.loads(out) if out.strip() else None
        except ValueError:
            resp = None
        if not isinstance(resp, dict):
            msg = _scrub(err or out or "empty response")
            raise GhError(f"graphql: {msg}", _classify(msg))
        errors = resp.get("errors") or []
        data = resp.get("data")
        if errors:
            types = {e.get("type", "") for e in errors}
            text = " ".join(str(e.get("message", "")) for e in errors)
            if "RATE_LIMITED" in types:
                raise GhError(f"graphql rate limited: {_scrub(text)}", "rate_limit")
            if data is None:
                raise GhError(f"graphql: {_scrub(text)}", _classify(text + " " + " ".join(types)))
        return data, errors


def _parse_included(out: str):
    if not out.startswith("HTTP/"):
        return None, {}, out
    m = re.search(r"\r?\n\r?\n", out)
    head, body = (out[: m.start()], out[m.end():]) if m else (out, "")
    lines = head.splitlines()
    try:
        status = int(lines[0].split()[1])
    except (IndexError, ValueError):
        status = None
    hdrs = {}
    for line in lines[1:]:
        if ":" in line:
            k, v = line.split(":", 1)
            hdrs[k.strip().lower()] = v.strip()
    return status, hdrs, body


def next_link(link_header: str | None) -> str | None:
    if not link_header:
        return None
    for part in link_header.split(","):
        m = re.match(r'\s*<([^>]+)>;\s*rel="next"', part)
        if m:
            return m.group(1).replace("https://api.github.com", "")
    return None
