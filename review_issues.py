#!/usr/bin/env python3
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

OWNER = os.environ.get("GH_OWNER", "MJP-76")
GH_TOKEN = os.environ.get("GH_TOKEN", "")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "")
WEBHOOK = os.environ.get("HA_WEBHOOK_URL", "")
MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.6-flash")
MAX_BODY = 1500
MAX_COMMENT = 800
MAX_COMMENTS = 5
MAX_MSG = 15000

API_VERSION = "2022-11-28"


def gh(url, retries=3):
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {GH_TOKEN}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": API_VERSION,
        },
    )
    return json.loads(_request(req, retries))


def gh_post(url, data, retries=3):
    req = urllib.request.Request(
        url,
        data=json.dumps(data).encode(),
        headers={
            "Authorization": f"Bearer {GH_TOKEN}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": API_VERSION,
            "Content-Type": "application/json",
        },
        method="POST",
    )
    return json.loads(_request(req, retries))


def gemini(payload, retries=3):
    req = urllib.request.Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent",
        data=json.dumps(payload).encode(),
        headers={
            "x-goog-api-key": GEMINI_KEY,
            "content-type": "application/json",
        },
        method="POST",
    )
    return json.loads(_request(req, retries))


def _request(req, retries):
    last = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return resp.read().decode()
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="replace")
            last = f"HTTP {e.code}: {body[:300]}"
            if e.code in (429, 500, 502, 503, 504) and attempt < retries - 1:
                time.sleep(2 * (attempt + 1))
                continue
            raise RuntimeError(last)
        except urllib.error.URLError as e:
            last = str(e)
            if attempt < retries - 1:
                time.sleep(2 * (attempt + 1))
                continue
            raise RuntimeError(last)
    raise RuntimeError(last or "request failed")


def list_repos():
    repos = []
    page = 1
    while True:
        batch = gh(
            f"https://api.github.com/users/{OWNER}/repos?per_page=100&page={page}&sort=updated"
        )
        if not batch:
            break
        repos.extend(r["name"] for r in batch if not r.get("fork"))
        if len(batch) < 100:
            break
        page += 1
    return sorted(repos)


def issue_comments(repo, number):
    try:
        comments = gh(
            f"https://api.github.com/repos/{OWNER}/{repo}/issues/{number}/comments?per_page=100"
        )
    except RuntimeError:
        return []
    return [c.get("body", "")[:MAX_COMMENT] for c in comments[-MAX_COMMENTS:]]


def open_issues(repo):
    items = gh(
        f"https://api.github.com/repos/{OWNER}/{repo}/issues?state=open&per_page=100"
    )
    issues = []
    for it in items:
        if "pull_request" in it:
            continue
        issues.append(
            {
                "repo": repo,
                "number": it["number"],
                "title": it["title"],
                "labels": [l["name"] for l in it.get("labels", [])],
                "body": (it.get("body") or "").strip()[:MAX_BODY],
                "updated": it.get("updated_at"),
                "comments": issue_comments(repo, it["number"]),
            }
        )
    return issues


SYSTEM_PROMPT = (
    "You are a senior code reviewer and Home Assistant integration maintainer. "
    "You review GitHub issues for a user's Home Assistant integrations, add-ons and "
    "custom components and produce concise, actionable fix guidance. Be concrete and "
    "specific. Prefer the simplest robust fix. Do not invent code details you cannot "
    "see; if you need more info, say so. Keep the whole digest under 9000 characters."
)

USER_TEMPLATE = (
    "Below are the currently open GitHub issues across the user's repositories, as JSON. "
    "For each issue produce a short markdown report section. Output ONLY the report, "
    "no preamble.\n\n"
    "Format per issue, inside a '## repo - title (#number)' heading:\n"
    "- **Type:** bug | feature request | question | housekeeping\n"
    "- **Priority:** High / Medium / Low\n"
    "- **Diagnosis:** one or two lines on what the problem actually is\n"
    "- **Suggested fix:** concrete, actionable steps to fix or respond\n\n"
    "Group issues by repository. If there are no issues, output exactly: 'No open issues.'\n\n"
    "Issues:\n{issues}"
)


def analyze(issues):
    payload = {
        "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": [
            {
                "role": "user",
                "parts": [
                    {
                        "text": USER_TEMPLATE.format(
                            issues=json.dumps(issues, indent=2)
                        )
                    }
                ],
            }
        ],
        "generationConfig": {"maxOutputTokens": 4000},
    }
    resp = gemini(payload)
    candidates = resp.get("candidates") or []
    if not candidates:
        raise RuntimeError("Gemini returned no candidates: " + json.dumps(resp)[:300])
    parts = candidates[0].get("content", {}).get("parts") or []
    return "".join(part.get("text", "") for part in parts)


def post_webhook(title, message):
    if not WEBHOOK:
        return
    message = message[:MAX_MSG]
    if len(message) > MAX_MSG - 50:
        message += "\n\n_[truncated — see full report in All-Repo-Info workflow artifacts]_"
    data = {"title": title, "message": message}
    req = urllib.request.Request(
        WEBHOOK,
        data=json.dumps(data).encode(),
        headers={
            "Content-Type": "application/json",
            "User-Agent": "curl/8.4.0",
        },
        method="POST",
    )
    _request(req, 2)


def main():
    if not GH_TOKEN:
        sys.exit("GH_TOKEN not set")
    if not GEMINI_KEY:
        sys.exit("GEMINI_API_KEY not set")
    if not WEBHOOK:
        sys.exit("HA_WEBHOOK_URL not set")

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    issues = []
    for repo in list_repos():
        issues.extend(open_issues(repo))
    issues.sort(key=lambda i: (i["repo"], i["number"]))

    if not issues:
        report = "No open issues."
        title = f"GitHub Issue Review — all clear ({now})"
    else:
        report = analyze(issues).strip()
        title = f"GitHub Issue Review — {len(issues)} open ({now})"

    with open("review_report.md", "w") as f:
        f.write(f"# GitHub Issue Review — {now}\n\n{report}\n")

    post_webhook(title, report)
    print(f"Reported {len(issues)} issue(s) to HA webhook")
    print(title)


if __name__ == "__main__":
    main()
