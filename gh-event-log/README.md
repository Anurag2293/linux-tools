# gh-event-log

Logs your GitHub pull-request activity into SQLite and serves it read-only over your
[Tailscale](https://tailscale.com) tailnet, so an assistant or script on another tailnet host can
follow reviews, comments, CI results and merges without holding GitHub credentials of its own.

It talks to GitHub only through the `gh` CLI you have already authenticated. That makes it work in
orgs that enforce SAML SSO and do not approve third-party apps or personal access tokens: if
`gh pr list` works for you, this works. The token never enters this process; every call shells out
to `gh api`.

It only reads from GitHub. It never comments, reviews, merges or pushes.

Dependencies: Python 3.8+ (standard library only), `gh`, and `tailscale` for the HTTP API.

## What it polls

Every `poll_interval_s` (120 s by default):

1. **Notifications**: `GET /notifications?all=true&participating=false&since=…`, sending
   `If-Modified-Since` from the previous `Last-Modified` and not polling faster than
   `X-Poll-Interval`. Each notification becomes an event (`kind` = `mentioned` for mentions,
   otherwise `notification`), and the PR it points at is tracked.
2. **PR search** (GraphQL `search`), per org in `orgs`, or across all of GitHub when `orgs` is
   empty:
   - `author:@me is:open` and `author:@me updated:>=<window>`
   - `review-requested:@me is:open` (includes team requests)
   - `reviewed-by:@me updated:>=<window>`

   The window starts one hour before the last successful search and never reaches back further
   than `backfill_days`.
3. **PR details** (GraphQL, 8 PRs per query) for every PR whose `updatedAt` changed, every PR a
   new notification points at, every open PR whose CI is still running, and, every
   `full_refresh_every` polls, every open PR updated in the last `track_open_days`. Each query
   returns reviews with their inline comments, the timeline (issue comments, review requests,
   commits, force pushes, merge, close, reopen, draft changes), requested reviewers, the review
   decision and the head commit's check runs and statuses.

Cost, measured on an account with about 220 PRs in the 14-day window: the first backfill uses
about 30 GraphQL points, and steady polling every 2 minutes about 300 points per hour, or 7% of
the 5,000-point hourly budget it shares with your own `gh` use. REST use is one notifications
call per poll. The collector pauses itself when fewer than `graphql_min_remaining` or
`rest_min_remaining` calls are left.

Failures never crash the service. gh auth or SSO errors back off 5 minutes, rate limits sleep
until the reset time, and other errors back off exponentially up to `max_backoff_s`. `/health`
reports the last error.

## Data

The database lives at `~/.local/share/gh-event-log/events.db` (SQLite, WAL mode).

### `events`

| column | meaning |
|---|---|
| `seq` | increasing integer; use it as a high-water mark. It has gaps, so don't count with it |
| `id` | stable unique id, `<owner/repo>#<n>:<kind>:<github id>`; inserts are `INSERT OR IGNORE` |
| `ts` | when it happened on GitHub (UTC, ISO 8601) |
| `observed_at` | when the collector first saw it |
| `repo`, `number`, `pr_title` | the PR (or issue, for some notifications) |
| `kind` | see below |
| `actor` | GitHub login that acted, if known |
| `body` | text, truncated to `body_max_chars` (4000) |
| `url` | link to the comment, review, commit or PR |
| `my_relation` | `author`, `requested_reviewer`, `reviewer`, `commenter`, `mentioned`, `subscribed` or `other` |
| `source` | `timeline`, `review`, `ci` or `notification` |

Kinds: `opened`, `review_approved`, `changes_requested`, `review_commented`, `review_dismissed`,
`review_comment` (inline; the body starts with `[path:line]`), `comment`, `review_requested`,
`review_request_removed`, `pushed` (one per commit), `force_pushed`, `ci_status`, `merged`,
`closed`, `reopened`, `ready_for_review`, `converted_to_draft`, `mentioned`, `notification`.

`ci_status` is recorded once per head SHA and set of check results, and only when the rollup is
`SUCCESS`, `FAILURE` or `ERROR`; its body lists the failed checks.

`seq` follows insertion order, not `ts`: the first backfill inserts old events with new `seq`s.

### `prs`

The current state of each PR: title, state (`OPEN`, `CLOSED` or `MERGED`), draft flag, author,
branches, head SHA, review decision, mergeable, requested reviewers, latest review per reviewer,
CI rollup state and per-check results, `relation` (the strongest one) and `relations` (all of
them).

## HTTP API

GET only, JSON. The server binds only to this machine's tailnet IPv4 (`tailscale ip -4`, retried
until tailscaled is up) on port 8787, never to `0.0.0.0` or localhost. It answers only clients
whose source IP is in `allowed_ips` and, when `require_tailscale_tags` is set, whose
`tailscale whois` tags include all of those tags. Every other client gets `403`, and other methods
get `405`. With `allowed_ips` empty, the API is off.

| endpoint | parameters |
|---|---|
| `/health` | none. `ok` is true when the last poll succeeded within 3 intervals and gh auth works |
| `/events` | `since` (event `seq`, or ISO time or date), `repo` (`name` or `owner/name`), `number`, `kind` (comma list), `relation`, `limit` (default 100, max 1000), `order=desc` |
| `/prs` | `state` (`open` by default, `closed`, `merged`, `all`), `relation` (`author`, `review_requested`, `reviewer`, …), `repo`, `limit`, `checks=full` |
| `/prs/<owner>/<repo>/<number>` | `limit` for the attached events, newest first |

`/events` returns `{"events": [...], "count", "has_more", "next_since"}`. To follow the log, keep
the last `next_since` and call `/events?since=<it>` until `has_more` is false.

From an allowed host, with `100.64.0.1` standing for this machine's tailnet IP:

```sh
curl -s http://100.64.0.1:8787/health
curl -s 'http://100.64.0.1:8787/events?since=0&limit=200'
curl -s 'http://100.64.0.1:8787/events?since=2026-01-01T00:00:00Z&kind=review_approved,changes_requested,comment'
curl -s 'http://100.64.0.1:8787/prs?state=open&relation=review_requested'
curl -s 'http://100.64.0.1:8787/prs/my-org/my-repo/123'
```

An event:

```json
{"seq": 2539, "id": "my-org/my-repo#123:merged:ME_kwDO…", "ts": "2026-01-16T08:03:26Z",
 "observed_at": "2026-01-16T08:05:01Z", "repo": "my-org/my-repo", "number": 123,
 "pr_title": "ci: move release CI to app tokens", "kind": "merged", "actor": "octocat",
 "body": "into main as 13739a26fe", "url": "https://github.com/my-org/my-repo/pull/123",
 "my_relation": "author", "source": "timeline"}
```

The tailnet policy must also let the client reach port 8787 on this machine. A rule like
`{"action": "accept", "src": ["tag:my-agent"], "dst": ["my-machine:8787"]}` does it. Don't expose
the port with Funnel.

## Install

```sh
./install.sh
```

The script links `gh-event-log.service` into `~/.config/systemd/user`, writes a starter
`~/.config/gh-event-log/config.json` if there is none, enables lingering so the service runs
without a login session, and starts the service. Then edit the config (see
`config.example.json`) and restart:

```sh
systemctl --user restart gh-event-log
systemctl --user status gh-event-log
journalctl --user -u gh-event-log -f
./uninstall.sh    # removes the unit; keeps config and data
```

One poll into a scratch database, without the HTTP server:

```sh
echo '{"db_path": "/tmp/ghlog-test.db"}' > /tmp/ghlog.json
python3 -m gh_event_log --config /tmp/ghlog.json --once
```

## Configuration

`~/.config/gh-event-log/config.json` overrides the defaults in `gh_event_log/config.py`. Unknown
keys are rejected.

| key | default | meaning |
|---|---|---|
| `orgs` | `[]` | orgs to search; empty searches everywhere |
| `poll_interval_s` | 120 | seconds between polls |
| `backfill_days` | 14 | how far back the first run, or a run after downtime, looks |
| `track_open_days` | 60 | open PRs untouched for longer are no longer refreshed |
| `full_refresh_every` | 10 | refresh all tracked open PRs every N polls |
| `allowed_ips` | `[]` | client IPs the API answers; empty turns the API off |
| `require_tailscale_tags` | `[]` | tags the client must carry, checked with `tailscale whois` |
| `bind_host` | `tailscale` | `tailscale` resolves the tailnet IPv4 at start; wildcard addresses are refused |
| `bind_port` | 8787 | |
| `db_path` | `~/.local/share/gh-event-log/events.db` | |

## Caveats

- If `gh` keeps its token in the desktop keyring, the keyring may stay locked after a reboot until
  someone logs in. Until then `/health` shows `gh_auth_ok: false` and the collector retries every
  5 minutes. `gh auth login --insecure-storage` stores the token in a file instead.
- Each fetch reads only the last 100 timeline items, 50 reviews (50 inline comments each) and 100
  checks per PR. Polling every 2 minutes keeps up with any normal PR.
