from __future__ import annotations

import hashlib
import logging
import re
import time
from datetime import datetime, timedelta, timezone

from . import db
from .gh import Gh, GhError, next_link

log = logging.getLogger("collector")

RELATION_ORDER = ["author", "requested_reviewer", "reviewer", "commenter", "mentioned", "subscribed"]
CI_TERMINAL = {"SUCCESS", "FAILURE", "ERROR"}
NOTIF_REASON_RELATION = {
    "author": "author",
    "review_requested": "requested_reviewer",
    "comment": "commenter",
    "mention": "mentioned",
    "team_mention": "mentioned",
    "subscribed": "subscribed",
    "manual": "subscribed",
    "assign": "assignee",
    "state_change": "subscribed",
    "ci_activity": "author",
}

SEARCH_QUERY = """
query($q: String!, $after: String) {
  viewer { login }
  rateLimit { remaining resetAt cost limit }
  search(type: ISSUE, query: $q, first: 100, after: $after) {
    issueCount
    pageInfo { hasNextPage endCursor }
    nodes { ... on PullRequest { number updatedAt state repository { nameWithOwner } } }
  }
}
"""

ACTOR = "actor { login }"
REVIEWER = "requestedReviewer { __typename ... on User { login } ... on Team { slug } ... on Bot { login } ... on Mannequin { login } }"

PR_FRAGMENT = f"""
fragment PRF on PullRequest {{
  number title url state isDraft createdAt updatedAt mergedAt closedAt
  repository {{ nameWithOwner }}
  author {{ login }}
  headRefName baseRefName headRefOid reviewDecision mergeable
  reviewRequests(first: 30) {{ nodes {{ {REVIEWER} }} }}
  latestReviews(first: 30) {{ nodes {{ author {{ login }} state submittedAt }} }}
  commits(last: 1) {{ nodes {{ commit {{
    oid committedDate
    statusCheckRollup {{ state contexts(first: 100) {{ nodes {{
      __typename
      ... on CheckRun {{ databaseId name status conclusion startedAt completedAt detailsUrl }}
      ... on StatusContext {{ id context state createdAt targetUrl description }}
    }} }} }}
  }} }} }}
  reviews(last: 50) {{ nodes {{
    databaseId state body submittedAt createdAt url author {{ login }}
    comments(first: 50) {{ nodes {{ databaseId body createdAt url path line originalLine author {{ login }} }} }}
  }} }}
  timelineItems(last: 100, itemTypes: [ISSUE_COMMENT, REVIEW_REQUESTED_EVENT, REVIEW_REQUEST_REMOVED_EVENT,
      PULL_REQUEST_COMMIT, HEAD_REF_FORCE_PUSHED_EVENT, MERGED_EVENT, CLOSED_EVENT, REOPENED_EVENT,
      READY_FOR_REVIEW_EVENT, CONVERT_TO_DRAFT_EVENT]) {{ nodes {{
    __typename
    ... on IssueComment {{ databaseId body createdAt url author {{ login }} }}
    ... on ReviewRequestedEvent {{ id createdAt {ACTOR} {REVIEWER} }}
    ... on ReviewRequestRemovedEvent {{ id createdAt {ACTOR} {REVIEWER} }}
    ... on PullRequestCommit {{ id url commit {{ oid messageHeadline committedDate author {{ name user {{ login }} }} }} }}
    ... on HeadRefForcePushedEvent {{ id createdAt {ACTOR} beforeCommit {{ oid }} afterCommit {{ oid }} }}
    ... on MergedEvent {{ id createdAt {ACTOR} mergeRefName commit {{ oid }} }}
    ... on ClosedEvent {{ id createdAt {ACTOR} }}
    ... on ReopenedEvent {{ id createdAt {ACTOR} }}
    ... on ReadyForReviewEvent {{ id createdAt {ACTOR} }}
    ... on ConvertToDraftEvent {{ id createdAt {ACTOR} }}
  }} }}
}}
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_ts(s: str | None) -> datetime | None:
    if not s:
        return None
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def login(obj) -> str | None:
    return (obj or {}).get("login") if obj else None


def reviewer_name(rr) -> str | None:
    if not rr:
        return None
    if rr.get("__typename") == "Team":
        return "team:" + rr.get("slug", "?")
    return rr.get("login")


class Collector:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.gh = Gh(cfg["gh_bin"])
        self.conn = db.connect(cfg["db_path"])
        self.me = db.get_meta(self.conn, "me")
        self.poll_count = 0
        self.failures = 0
        self.review_requested_set = {tuple(k) for k in db.get_meta(self.conn, "review_requested_set", [])}
        self.next_notif_poll = 0.0

    # ---------------------------------------------------------------- loop

    def run_forever(self, once: bool = False) -> None:
        while True:
            started = time.time()
            delay = self.cfg["poll_interval_s"]
            try:
                self.poll_once()
                self.failures = 0
            except GhError as e:
                self.failures += 1
                delay = self._backoff(e)
                self._record_error(e.kind, str(e))
                log.warning("poll failed (%s): %s; retrying in %ss", e.kind, e, int(delay))
            except Exception as e:
                self.failures += 1
                delay = self._backoff(None)
                self._record_error("internal", f"{type(e).__name__}: {e}")
                log.exception("poll crashed; retrying in %ss", int(delay))
            if once:
                return
            self._set_meta(next_poll_at=iso(datetime.now(timezone.utc) + timedelta(seconds=delay)))
            time.sleep(max(5.0, delay - (time.time() - started) if self.failures == 0 else delay))

    def _backoff(self, err: GhError | None) -> float:
        base = self.cfg["poll_interval_s"]
        cap = self.cfg["max_backoff_s"]
        if err is not None and err.kind == "rate_limit" and err.reset_at:
            return min(cap * 2, max(base, err.reset_at - time.time() + 10))
        if err is not None and err.kind in ("auth", "sso"):
            return max(base, 300)
        return min(cap, base * (2 ** min(self.failures, 8)))

    def _set_meta(self, **kv) -> None:
        for k, v in kv.items():
            db.set_meta(self.conn, k, v)
        self.conn.commit()

    def _record_error(self, kind: str, msg: str) -> None:
        self._set_meta(
            last_error={"at": now_iso(), "kind": kind, "message": msg[:500]},
            consecutive_failures=self.failures,
            gh_auth_ok=(kind not in ("auth", "sso")) and self._auth_ok_quiet(kind),
        )

    def _auth_ok_quiet(self, kind: str) -> bool:
        if kind in ("auth", "sso"):
            return False
        try:
            return self.gh.auth_ok()
        except GhError:
            return False

    # ---------------------------------------------------------------- poll

    def poll_once(self) -> None:
        self.poll_count += 1
        t0 = time.time()
        attempt_at = now_iso()
        self._set_meta(last_poll_attempt_at=attempt_at)

        notif_prs = self.poll_notifications()
        search_hits = self.search_prs()

        to_fetch = {}
        for key, upd in search_hits.items():
            row = db.get_pr(self.conn, *key)
            if row is None or row["updated_at"] != upd:
                to_fetch[key] = "search"
        for key, upd in notif_prs.items():
            row = db.get_pr(self.conn, *key)
            if row is None or (row["last_fetched_at"] or "") < upd:
                to_fetch.setdefault(key, "notification")
        full = self.poll_count % self.cfg["full_refresh_every"] == 1
        cutoff = iso(datetime.now(timezone.utc) - timedelta(days=self.cfg["track_open_days"]))
        for row in self.conn.execute(
            "SELECT * FROM prs WHERE state='OPEN' AND updated_at >= ?", (cutoff,)
        ).fetchall():
            key = (row["repo"], row["number"])
            if key in to_fetch:
                continue
            if full or self._ci_unsettled(row):
                to_fetch[key] = "refresh"

        added = self.fetch_details(list(to_fetch))
        counts = self.conn.execute(
            "SELECT (SELECT COUNT(*) FROM events) e, (SELECT COUNT(*) FROM prs) p,"
            " (SELECT COUNT(*) FROM prs WHERE state='OPEN') o, (SELECT MAX(seq) FROM events) s"
        ).fetchone()
        self._set_meta(
            last_poll_ok_at=now_iso(),
            last_poll_duration_s=round(time.time() - t0, 1),
            last_poll_stats={
                "prs_fetched": len(to_fetch),
                "events_added": added,
                "full_refresh": full,
            },
            gh_auth_ok=True,
            consecutive_failures=0,
        )
        log.info(
            "poll ok: fetched %d PRs, +%d events (total events=%d, prs=%d, open=%d, max_seq=%s) in %.1fs",
            len(to_fetch), added, counts["e"], counts["p"], counts["o"], counts["s"], time.time() - t0,
        )

    def _ci_unsettled(self, row) -> bool:
        state = row["ci_state"]
        if state in ("PENDING", "EXPECTED"):
            return True
        if state is None:
            committed = parse_ts(row["head_committed_at"])
            return committed is not None and datetime.now(timezone.utc) - committed < timedelta(minutes=45)
        return False

    # ------------------------------------------------------- notifications

    def poll_notifications(self) -> dict:
        """Returns {(repo, number): notification updated_at} for org PRs seen."""
        if time.time() < self.next_notif_poll:
            return {}
        since = db.get_meta(self.conn, "notif_since")
        if not since:
            since = iso(datetime.now(timezone.utc) - timedelta(days=self.cfg["backfill_days"]))
        last_modified = db.get_meta(self.conn, "notif_last_modified")
        path = f"/notifications?all=true&participating=false&per_page=50&since={since}"
        headers = {"If-Modified-Since": last_modified} if last_modified else {}
        poll_started = datetime.now(timezone.utc)
        items = []
        first_hdrs = {}
        for page in range(20):
            status, hdrs, body = self.gh.rest_get(path, headers if page == 0 else None)
            if page == 0:
                first_hdrs = hdrs
            if status == 304:
                break
            items.extend(body or [])
            path = next_link(hdrs.get("link"))
            if not path:
                break
        self._check_rest_budget(first_hdrs)
        try:
            interval = int(first_hdrs.get("x-poll-interval", "60"))
        except ValueError:
            interval = 60
        self.next_notif_poll = time.time() + interval

        orgs = {o.lower() for o in self.cfg["orgs"]}
        events, prs = [], {}
        for n in items:
            repo = n["repository"]["full_name"]
            subj = n.get("subject") or {}
            m = re.search(r"/(pulls|issues)/(\d+)$", subj.get("url") or "")
            number = int(m.group(2)) if m else None
            kind_path = "pull" if subj.get("type") == "PullRequest" else "issues"
            url = f"https://github.com/{repo}/{kind_path}/{number}" if number else n["repository"].get("html_url")
            reason = n.get("reason", "")
            events.append({
                "id": f"{repo}#{number or 0}:notification:{n['id']}@{n['updated_at']}",
                "ts": n["updated_at"],
                "observed_at": now_iso(),
                "repo": repo,
                "number": number,
                "pr_title": subj.get("title"),
                "kind": "mentioned" if reason in ("mention", "team_mention") else "notification",
                "actor": None,
                "body": f"{reason}: {subj.get('type')}: {subj.get('title')}",
                "url": url,
                "my_relation": NOTIF_REASON_RELATION.get(reason, reason),
                "source": "notification",
            })
            if subj.get("type") == "PullRequest" and number and (not orgs or repo.split("/")[0].lower() in orgs):
                key = (repo, number)
                prs[key] = max(prs.get(key, ""), n["updated_at"])
                self._add_notif_reason(key, reason)
        added = db.insert_events(self.conn, events)
        meta = {"notif_since": iso(poll_started - timedelta(minutes=5)), "last_notif_poll_at": now_iso()}
        if first_hdrs.get("last-modified"):
            meta["notif_last_modified"] = first_hdrs["last-modified"]
        self._set_meta(**meta)
        if items:
            log.info("notifications: %d items, +%d events", len(items), added)
        return prs

    def _add_notif_reason(self, key, reason: str) -> None:
        row = db.get_pr(self.conn, *key)
        if row is None:
            self.conn.execute(
                "INSERT INTO prs(repo, number, notif_reasons) VALUES(?,?,?)", (key[0], key[1], reason)
            )
            return
        reasons = set(filter(None, (row["notif_reasons"] or "").split(",")))
        if reason not in reasons:
            reasons.add(reason)
            self.conn.execute(
                "UPDATE prs SET notif_reasons=? WHERE repo=? AND number=?",
                (",".join(sorted(reasons)), key[0], key[1]),
            )

    def _check_rest_budget(self, hdrs: dict) -> None:
        try:
            remaining = int(hdrs.get("x-ratelimit-remaining", "5000"))
            reset = float(hdrs.get("x-ratelimit-reset", "0"))
        except ValueError:
            return
        self._set_meta(rest_rate_limit={"remaining": remaining, "reset_at": iso(datetime.fromtimestamp(reset, timezone.utc)) if reset else None})
        if remaining < self.cfg["rest_min_remaining"]:
            raise GhError(f"REST budget low ({remaining} left), pausing", "rate_limit", reset or None)

    # -------------------------------------------------------------- search

    def search_prs(self) -> dict:
        """Returns {(repo, number): updatedAt} for every PR found by the searches."""
        last_ok = parse_ts(db.get_meta(self.conn, "last_search_ok_at"))
        floor = datetime.now(timezone.utc) - timedelta(days=self.cfg["backfill_days"])
        window = max(floor, last_ok - timedelta(hours=1)) if last_ok else floor
        since = window.strftime("%Y-%m-%dT%H:%M:%SZ")
        hits = {}
        requested = set()
        for org in self.cfg["orgs"] or [None]:
            base = f"is:pr org:{org}" if org else "is:pr"
            queries = {
                "author_open": f"{base} author:@me is:open",
                "author_recent": f"{base} author:@me updated:>={since}",
                "review_requested": f"{base} review-requested:@me is:open",
                "reviewed_by": f"{base} reviewed-by:@me updated:>={since}",
            }
            for name, q in queries.items():
                for node in self._search_all(q):
                    if not node:
                        continue
                    key = (node["repository"]["nameWithOwner"], node["number"])
                    hits[key] = node["updatedAt"]
                    if name == "review_requested":
                        requested.add(key)
        self.review_requested_set = requested
        self._set_meta(
            last_search_ok_at=now_iso(),
            review_requested_set=sorted([list(k) for k in requested]),
        )
        return hits

    def _search_all(self, q: str) -> list:
        nodes, after = [], None
        for _ in range(10):
            data, _errors = self.gh.graphql(SEARCH_QUERY, {"q": q, "after": after})
            self._note_graphql(data)
            if not self.me and data.get("viewer"):
                self.me = data["viewer"]["login"]
                self._set_meta(me=self.me)
            s = data["search"]
            nodes.extend(s["nodes"])
            if not s["pageInfo"]["hasNextPage"]:
                break
            after = s["pageInfo"]["endCursor"]
        return nodes

    def _note_graphql(self, data: dict) -> None:
        rl = (data or {}).get("rateLimit")
        if not rl:
            return
        self._set_meta(graphql_rate_limit=rl)
        if rl["remaining"] < self.cfg["graphql_min_remaining"]:
            reset = parse_ts(rl["resetAt"])
            raise GhError(
                f"GraphQL budget low ({rl['remaining']} left), pausing",
                "rate_limit",
                reset.timestamp() if reset else None,
            )

    # ------------------------------------------------------------- details

    def fetch_details(self, keys: list) -> int:
        added = 0
        bs = self.cfg["detail_batch_size"]
        for i in range(0, len(keys), bs):
            batch = keys[i:i + bs]
            parts = []
            for j, (repo, number) in enumerate(batch):
                owner, name = repo.split("/", 1)
                parts.append(
                    f'p{j}: repository(owner: "{_gql_str(owner)}", name: "{_gql_str(name)}") '
                    f"{{ pullRequest(number: {int(number)}) {{ ...PRF }} }}"
                )
            query = PR_FRAGMENT + "query {\n rateLimit { remaining resetAt cost limit }\n " + "\n ".join(parts) + "\n}"
            data, errors = self.gh.graphql(query)
            for e in errors:
                log.warning("graphql partial error: %s", str(e.get("message"))[:300])
            for j, key in enumerate(batch):
                pr = ((data or {}).get(f"p{j}") or {}).get("pullRequest")
                if not pr:
                    log.warning("PR %s#%s not returned; skipping", *key)
                    continue
                added += self._store_pr(pr)
            self.conn.commit()
            self._note_graphql(data)
        return added

    def _store_pr(self, pr: dict) -> int:
        me = self.me
        repo = pr["repository"]["nameWithOwner"]
        number = pr["number"]
        key = (repo, number)
        old = db.get_pr(self.conn, repo, number)
        notif_reasons = set(filter(None, ((old["notif_reasons"] if old else "") or "").split(",")))

        head = ((pr.get("commits") or {}).get("nodes") or [{}])[0].get("commit") or {}
        rollup = head.get("statusCheckRollup") or {}
        checks = [_check_summary(c) for c in ((rollup.get("contexts") or {}).get("nodes") or []) if c]
        requested = [reviewer_name(r.get("requestedReviewer")) for r in (pr["reviewRequests"]["nodes"] or [])]
        reviews = [r for r in (pr["reviews"]["nodes"] or []) if r]
        timeline = [t for t in (pr["timelineItems"]["nodes"] or []) if t]

        rels = set()
        if login(pr.get("author")) == me:
            rels.add("author")
        if me in requested or key in self.review_requested_set:
            rels.add("requested_reviewer")
        if any(login(r.get("author")) == me and r.get("state") != "PENDING" for r in reviews):
            rels.add("reviewer")
        if any(t["__typename"] == "IssueComment" and login(t.get("author")) == me for t in timeline) or any(
            login(c.get("author")) == me for r in reviews for c in (r["comments"]["nodes"] or [])
        ):
            rels.add("commenter")
        for reason in notif_reasons:
            rels.add("mentioned" if NOTIF_REASON_RELATION.get(reason) == "mentioned" else "subscribed")
        relation = next((r for r in RELATION_ORDER if r in rels), "other")

        db.upsert_pr(self.conn, {
            "repo": repo,
            "number": number,
            "title": pr["title"],
            "url": pr["url"],
            "state": pr["state"],
            "is_draft": int(bool(pr["isDraft"])),
            "author": login(pr.get("author")),
            "created_at": pr["createdAt"],
            "updated_at": pr["updatedAt"],
            "merged_at": pr.get("mergedAt"),
            "closed_at": pr.get("closedAt"),
            "head_ref": pr["headRefName"],
            "base_ref": pr["baseRefName"],
            "head_sha": pr["headRefOid"],
            "head_committed_at": head.get("committedDate"),
            "review_decision": pr.get("reviewDecision"),
            "mergeable": pr.get("mergeable"),
            "requested_reviewers": requested,
            "latest_reviews": [
                {"author": login(r.get("author")), "state": r["state"], "submitted_at": r.get("submittedAt")}
                for r in (pr["latestReviews"]["nodes"] or []) if r
            ],
            "ci_state": rollup.get("state"),
            "ci_checks": checks,
            "relation": relation,
            "relations": ",".join(r for r in RELATION_ORDER if r in rels),
            "notif_reasons": ",".join(sorted(notif_reasons)),
            "last_fetched_at": now_iso(),
        })
        events = self._pr_events(pr, repo, number, relation, reviews, timeline, head, rollup, checks)
        return db.insert_events(self.conn, events)

    def _pr_events(self, pr, repo, number, relation, reviews, timeline, head, rollup, checks) -> list:
        me = self.me
        maxlen = self.cfg["body_max_chars"]
        observed = now_iso()
        prefix = f"{repo}#{number}"
        out = []

        def ev(kind, gid, ts, actor=None, body=None, url=None, rel=None, source="timeline"):
            if body is not None and len(body) > maxlen:
                body = body[:maxlen] + "…[truncated]"
            out.append({
                "id": f"{prefix}:{kind}:{gid}",
                "ts": ts or observed,
                "observed_at": observed,
                "repo": repo,
                "number": number,
                "pr_title": pr["title"],
                "kind": kind,
                "actor": actor,
                "body": body,
                "url": url or pr["url"],
                "my_relation": rel or relation,
                "source": source,
            })

        ev("opened", number, pr["createdAt"], login(pr.get("author")), None, pr["url"])

        review_kind = {
            "APPROVED": "review_approved",
            "CHANGES_REQUESTED": "changes_requested",
            "COMMENTED": "review_commented",
            "DISMISSED": "review_dismissed",
        }
        for r in reviews:
            state = r.get("state")
            if state == "PENDING":
                continue
            kind = review_kind.get(state, "review_" + str(state).lower())
            body = (r.get("body") or "").strip()
            if not (kind == "review_commented" and not body):
                ev(kind, r["databaseId"], r.get("submittedAt") or r.get("createdAt"),
                   login(r.get("author")), body or None, r.get("url"), source="review")
            for c in r["comments"]["nodes"] or []:
                if not c:
                    continue
                loc = c.get("path") or ""
                line = c.get("line") or c.get("originalLine")
                if line:
                    loc += f":{line}"
                ev("review_comment", c["databaseId"], c.get("createdAt"), login(c.get("author")),
                   f"[{loc}] {c.get('body') or ''}", c.get("url"), source="review")

        for t in timeline:
            tn = t["__typename"]
            if tn == "IssueComment":
                ev("comment", t["databaseId"], t["createdAt"], login(t.get("author")), t.get("body"), t.get("url"))
            elif tn in ("ReviewRequestedEvent", "ReviewRequestRemovedEvent"):
                who = reviewer_name(t.get("requestedReviewer"))
                kind = "review_requested" if tn == "ReviewRequestedEvent" else "review_request_removed"
                rel = "requested_reviewer" if who == me and kind == "review_requested" else None
                ev(kind, t["id"], t["createdAt"], login(t.get("actor")), f"reviewer: {who}", rel=rel)
            elif tn == "PullRequestCommit":
                c = t["commit"]
                author = login((c.get("author") or {}).get("user")) or (c.get("author") or {}).get("name")
                ev("pushed", c["oid"], c.get("committedDate"), author,
                   f"{c['oid'][:10]} {c.get('messageHeadline') or ''}", t.get("url"))
            elif tn == "HeadRefForcePushedEvent":
                before = ((t.get("beforeCommit") or {}).get("oid") or "")[:10]
                after = ((t.get("afterCommit") or {}).get("oid") or "")[:10]
                ev("force_pushed", t["id"], t["createdAt"], login(t.get("actor")), f"{before} -> {after}")
            elif tn == "MergedEvent":
                ev("merged", t["id"], t["createdAt"], login(t.get("actor")),
                   f"into {t.get('mergeRefName')} as {((t.get('commit') or {}).get('oid') or '')[:10]}")
            else:
                kind = {
                    "ClosedEvent": "closed",
                    "ReopenedEvent": "reopened",
                    "ReadyForReviewEvent": "ready_for_review",
                    "ConvertToDraftEvent": "converted_to_draft",
                }.get(tn)
                if kind:
                    ev(kind, t["id"], t["createdAt"], login(t.get("actor")))

        state = rollup.get("state")
        if state in CI_TERMINAL and head.get("oid"):
            sha = head["oid"]
            sig = hashlib.sha1(
                "|".join(sorted(f"{c['name']}:{c.get('id')}:{c['result']}" for c in checks)).encode()
            ).hexdigest()[:8]
            failed = [c for c in checks if c["result"] in ("FAILURE", "ERROR", "TIMED_OUT", "CANCELLED", "ACTION_REQUIRED", "STARTUP_FAILURE")]
            lines = [f"{state} on {sha[:10]}: {len(checks)} checks, {len(failed)} failed"]
            lines += [f"- {c['name']}: {c['result']} {c.get('url') or ''}".rstrip() for c in failed]
            done = [c.get("at") for c in checks if c.get("at")]
            ev("ci_status", f"{sha[:12]}-{state}-{sig}", max(done) if done else None, None, "\n".join(lines),
               (failed[0].get("url") if failed else None) or f"{pr['url']}/checks", source="ci")
        return out


def _check_summary(c: dict) -> dict:
    if c.get("__typename") == "CheckRun":
        return {
            "type": "check_run",
            "id": c.get("databaseId"),
            "name": c.get("name"),
            "status": c.get("status"),
            "result": c.get("conclusion") or c.get("status"),
            "at": c.get("completedAt") or c.get("startedAt"),
            "url": c.get("detailsUrl"),
        }
    return {
        "type": "status",
        "id": c.get("id"),
        "name": c.get("context"),
        "status": c.get("state"),
        "result": c.get("state"),
        "at": c.get("createdAt"),
        "url": c.get("targetUrl"),
        "description": c.get("description"),
    }


def _gql_str(s: str) -> str:
    if not re.match(r"^[A-Za-z0-9_.\-]+$", s):
        raise ValueError(f"unexpected characters in repo name: {s!r}")
    return s
