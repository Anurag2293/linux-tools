from __future__ import annotations

import json
import logging
import re
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

from . import db

log = logging.getLogger("server")

MAX_LIMIT = 1000
DEFAULT_LIMIT = 100
RELATION_ALIASES = {"review_requested": "requested_reviewer", "reviewed": "reviewer"}


class Whois:
    """Caches `tailscale whois` tag lookups per source IP."""

    def __init__(self, tailscale_bin: str, ttl: float = 300.0):
        self.bin = tailscale_bin
        self.ttl = ttl
        self.cache = {}
        self.lock = threading.Lock()

    def tags(self, ip: str):
        now = time.time()
        with self.lock:
            hit = self.cache.get(ip)
            if hit and now - hit[0] < self.ttl:
                return hit[1]
        try:
            p = subprocess.run([self.bin, "whois", "--json", ip], capture_output=True, text=True, timeout=10)
            tags = json.loads(p.stdout).get("Node", {}).get("Tags") or [] if p.returncode == 0 else None
        except (OSError, ValueError, subprocess.TimeoutExpired):
            tags = None
        with self.lock:
            self.cache[ip] = (now, tags)
        return tags


def make_handler(cfg: dict, whois: Whois):
    allowed = set(cfg["allowed_ips"])
    required_tags = set(cfg["require_tailscale_tags"])
    db_path = cfg["db_path"]

    class Handler(BaseHTTPRequestHandler):
        server_version = "gh-event-log/1"
        sys_version = ""

        def log_message(self, fmt, *args):
            log.info("%s %s", self.client_address[0], fmt % args)

        def _send(self, code: int, obj) -> None:
            body = json.dumps(obj, indent=None, separators=(",", ":"), ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _authorized(self) -> bool:
            ip = self.client_address[0]
            if ip not in allowed:
                return False
            if required_tags:
                tags = whois.tags(ip)
                if tags is None or not required_tags.issubset(set(tags)):
                    return False
            return True

        def _reject_method(self):
            if not self._authorized():
                return self._send(403, {"error": "forbidden"})
            self.send_response(405)
            self.send_header("Allow", "GET")
            self.send_header("Content-Length", "0")
            self.end_headers()

        do_POST = do_PUT = do_PATCH = do_DELETE = do_HEAD = do_OPTIONS = _reject_method

        def do_GET(self):
            if not self._authorized():
                return self._send(403, {"error": "forbidden"})
            url = urlsplit(self.path)
            q = {k: v[-1] for k, v in parse_qs(url.query).items()}
            path = url.path.rstrip("/") or "/"
            try:
                conn = db.connect_ro(db_path)
            except Exception:
                return self._send(503, {"error": "database not ready"})
            try:
                if path in ("/", "/health"):
                    return self._send(200, health(conn, cfg))
                if path == "/events":
                    return self._send(200, list_events(conn, q))
                if path == "/prs":
                    return self._send(200, list_prs(conn, q))
                m = re.match(r"^/prs/([^/]+)/([^/]+)/(\d+)$", path)
                if m:
                    res = one_pr(conn, f"{m.group(1)}/{m.group(2)}", int(m.group(3)), q)
                    return self._send(200 if res else 404, res or {"error": "not found"})
                return self._send(404, {"error": "not found", "endpoints": ["/health", "/events", "/prs", "/prs/<owner>/<repo>/<number>"]})
            except BadRequest as e:
                return self._send(400, {"error": str(e)})
            except Exception:
                log.exception("request failed: %s", url.path)
                return self._send(500, {"error": "internal error"})
            finally:
                conn.close()

    return Handler


class BadRequest(Exception):
    pass


def _limit(q: dict) -> int:
    try:
        n = int(q.get("limit", DEFAULT_LIMIT))
    except ValueError:
        raise BadRequest("limit must be an integer")
    return max(1, min(MAX_LIMIT, n))


def _repo_clause(repo: str | None):
    if not repo:
        return None, None
    if "/" in repo:
        return "repo = ? COLLATE NOCASE", repo
    escaped = repo.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return "repo LIKE ? ESCAPE '\\'", "%/" + escaped


def health(conn, cfg: dict) -> dict:
    meta = {r["key"]: json.loads(r["value"]) for r in conn.execute("SELECT key, value FROM meta")}
    c = conn.execute(
        "SELECT (SELECT COUNT(*) FROM events) events, (SELECT MAX(seq) FROM events) max_seq,"
        " (SELECT COUNT(*) FROM prs WHERE title IS NOT NULL) prs,"
        " (SELECT COUNT(*) FROM prs WHERE state='OPEN') open_prs,"
        " (SELECT MAX(ts) FROM events) latest_event_ts"
    ).fetchone()
    last_ok = meta.get("last_poll_ok_at")
    stale = True
    if last_ok:
        from .collector import parse_ts
        from datetime import datetime, timezone
        age = (datetime.now(timezone.utc) - parse_ts(last_ok)).total_seconds()
        stale = age > max(3 * cfg["poll_interval_s"], 600)
    return {
        "ok": bool(last_ok) and not stale and meta.get("gh_auth_ok", False),
        "gh_user": meta.get("me"),
        "gh_auth_ok": meta.get("gh_auth_ok"),
        "last_poll_ok_at": last_ok,
        "last_poll_attempt_at": meta.get("last_poll_attempt_at"),
        "next_poll_at": meta.get("next_poll_at"),
        "last_poll_stats": meta.get("last_poll_stats"),
        "consecutive_failures": meta.get("consecutive_failures", 0),
        "last_error": meta.get("last_error"),
        "poll_interval_s": cfg["poll_interval_s"],
        "orgs": cfg["orgs"],
        "rate_limit": {"graphql": meta.get("graphql_rate_limit"), "rest": meta.get("rest_rate_limit")},
        "counts": {"events": c["events"], "prs": c["prs"], "open_prs": c["open_prs"]},
        "max_seq": c["max_seq"] or 0,
        "latest_event_ts": c["latest_event_ts"],
    }


def _event_dict(r) -> dict:
    d = dict(r)
    return d


def list_events(conn, q: dict) -> dict:
    where, args = [], []
    since = q.get("since")
    if since:
        if since.isdigit():
            where.append("seq > ?")
            args.append(int(since))
        else:
            from .collector import parse_ts, iso
            try:
                ts = parse_ts(since if ("T" in since or since.endswith("Z")) else since + "T00:00:00Z")
            except ValueError:
                raise BadRequest("since must be an event seq (integer) or ISO-8601 timestamp")
            if ts.tzinfo is None:
                raise BadRequest("ISO since needs a timezone, e.g. 2026-11-17T00:00:00Z")
            where.append("ts >= ?")
            args.append(iso(ts))
    clause, val = _repo_clause(q.get("repo"))
    if clause:
        where.append(clause)
        args.append(val)
    if q.get("number"):
        if not q["number"].isdigit():
            raise BadRequest("number must be an integer")
        where.append("number = ?")
        args.append(int(q["number"]))
    if q.get("kind"):
        kinds = [k for k in q["kind"].split(",") if k]
        where.append(f"kind IN ({','.join('?' for _ in kinds)})")
        args += kinds
    if q.get("relation"):
        rel = RELATION_ALIASES.get(q["relation"], q["relation"])
        where.append("my_relation = ?")
        args.append(rel)
    limit = _limit(q)
    order = "DESC" if q.get("order") == "desc" else "ASC"
    sql = "SELECT * FROM events" + (" WHERE " + " AND ".join(where) if where else "")
    sql += f" ORDER BY seq {order} LIMIT ?"
    rows = conn.execute(sql, args + [limit + 1]).fetchall()
    has_more = len(rows) > limit
    rows = rows[:limit]
    events = [_event_dict(r) for r in rows]
    max_seq = max((e["seq"] for e in events), default=None)
    return {"events": events, "count": len(events), "has_more": has_more, "next_since": max_seq}


def list_prs(conn, q: dict) -> dict:
    where, args = ["title IS NOT NULL"], []
    state = (q.get("state") or "open").upper()
    if state != "ALL":
        if state not in ("OPEN", "CLOSED", "MERGED"):
            raise BadRequest("state must be open, closed, merged or all")
        where.append("state = ?")
        args.append(state)
    if q.get("relation"):
        rel = RELATION_ALIASES.get(q["relation"], q["relation"])
        where.append("(',' || relations || ',') LIKE ?")
        args.append(f"%,{rel},%")
    clause, val = _repo_clause(q.get("repo"))
    if clause:
        where.append(clause)
        args.append(val)
    limit = _limit(q)
    rows = conn.execute(
        "SELECT * FROM prs WHERE " + " AND ".join(where) + " ORDER BY updated_at DESC LIMIT ?",
        args + [limit],
    ).fetchall()
    prs = [db.pr_row_to_dict(r) for r in rows]
    if q.get("checks") != "full":
        for p in prs:
            p["ci_checks"] = _failed_checks(p.get("ci_checks"))
    return {"prs": prs, "count": len(prs)}


def _failed_checks(checks):
    if not checks:
        return checks
    bad = {"FAILURE", "ERROR", "TIMED_OUT", "CANCELLED", "ACTION_REQUIRED", "STARTUP_FAILURE"}
    return {
        "total": len(checks),
        "failed": [c for c in checks if c.get("result") in bad],
        "pending": [c["name"] for c in checks if c.get("result") in ("PENDING", "QUEUED", "IN_PROGRESS", "EXPECTED", "WAITING", "REQUESTED")],
    }


def one_pr(conn, repo: str, number: int, q: dict):
    row = conn.execute("SELECT * FROM prs WHERE repo = ? COLLATE NOCASE AND number = ?", (repo, number)).fetchone()
    if row is None or row["title"] is None:
        return None
    limit = _limit(q)
    events = conn.execute(
        "SELECT * FROM events WHERE repo = ? COLLATE NOCASE AND number = ? ORDER BY ts DESC, seq DESC LIMIT ?",
        (repo, number, limit),
    ).fetchall()
    return {"pr": db.pr_row_to_dict(row), "events": [_event_dict(e) for e in events]}


def resolve_bind_host(cfg: dict) -> str | None:
    host = cfg["bind_host"]
    if host != "tailscale":
        return host
    try:
        p = subprocess.run([cfg["tailscale_bin"], "ip", "-4"], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return None
    ip = p.stdout.strip().splitlines()[0] if p.returncode == 0 and p.stdout.strip() else None
    return ip if ip and ip.startswith("100.") else None


def serve_forever(cfg: dict, stop: threading.Event) -> None:
    if not cfg["allowed_ips"]:
        log.error("allowed_ips is empty in %s; HTTP API disabled", cfg["config_path"])
        return
    whois = Whois(cfg["tailscale_bin"])
    handler = make_handler(cfg, whois)
    delay = 5
    while not stop.is_set():
        host = resolve_bind_host(cfg)
        if not host:
            log.warning("tailnet IP not available yet; retrying in %ss", delay)
        else:
            try:
                httpd = ThreadingHTTPServer((host, cfg["bind_port"]), handler)
                httpd.daemon_threads = True
                log.info("listening on http://%s:%d (allowed=%s, tags=%s)", host, cfg["bind_port"],
                         cfg["allowed_ips"], cfg["require_tailscale_tags"])
                httpd.serve_forever()
                return
            except OSError as e:
                log.warning("cannot bind %s:%d (%s); retrying in %ss", host, cfg["bind_port"], e, delay)
        stop.wait(delay)
        delay = min(60, delay * 2)
