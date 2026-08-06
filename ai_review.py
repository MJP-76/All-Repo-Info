#!/usr/bin/env python3
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

OWNER = os.environ.get("GH_OWNER", "MJP-76")
GH_TOKEN = os.environ.get("GH_TOKEN", "")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "")
MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.6-flash")
TARGET_REPOS = [
    r.strip()
    for r in os.environ.get("TARGET_REPOS", "").split(",")
    if r.strip()
]
DRY_RUN = os.environ.get("DRY_RUN", "") == "1"
WORK_DIR = os.environ.get("REVIEW_WORKDIR", os.path.join(os.getcwd(), "repos"))

LABEL_AI = "ai-review"
LABEL_GEN = "generated"
BUDGET_PER_REPO = 200000
MAX_FILE_CHARS = 10000
MAX_FINDINGS = 10
SKIP_DIRS = {
    ".git", "node_modules", "__pycache__", "dist", "build", ".venv", "venv",
    ".github", ".mypy_cache", ".pytest_cache", ".tox", ".venv3", "html",
    "coverage", ".coverage", ".ruff_cache",
}
INCLUDE_EXTS = {".py", ".js", ".ts", ".tsx", ".yaml", ".yml", ".sh"}
INCLUDE_JSON = {"manifest.json", "hacs.json", "options.json", "configuration.json"}
SKIP_FILES = {
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock",
    "Pipfile.lock", "deno.lock", "requirements.txt", "LICENSE",
}
PRIORITY_DIR = "custom_components"

RESPONSE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "findings": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "title": {"type": "STRING"},
                    "file": {"type": "STRING"},
                    "location": {"type": "STRING"},
                    "severity": {"type": "STRING"},
                    "description": {"type": "STRING"},
                    "fix": {"type": "STRING"},
                },
                "required": ["title", "file", "location", "severity", "description", "fix"],
            },
        }
    },
    "required": ["findings"],
}

SYSTEM_PROMPT = (
    "You are a senior code reviewer for Home Assistant custom integrations and add-ons. "
    "Review the provided repository code and identify real, actionable problems only: "
    "bugs, security issues, error-handling gaps, concurrency problems, misuse of the "
    "Home Assistant integration framework, broken configuration, and similar genuine "
    "defects. Do NOT report cosmetic/style nits, speculative concerns, or false "
    "positives. Be precise about the exact file path and the function/class/line where "
    "the problem lives. Keep each finding concise. Prefer the most important findings. "
    "Titles must be short, specific, and stable (so the same finding gets the same "
    "title on repeat reviews). Report up to 10 findings; it is fine to report several "
    "findings per file. "
    "Files may be truncated for length: a line that reads '### TRUNCATED FOR REVIEW ###' "
    "marks the cut point. Ignore truncation artifacts such as apparent syntax errors, "
    "unclosed brackets, or dangling statements caused by the cut. Only report genuine "
    "problems."
)


def _request(req, retries=3):
    last = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                return resp.read().decode()
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="replace")
            last = f"HTTP {e.code}: {body[:400]}"
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


def gh_get(url):
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {GH_TOKEN}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    return json.loads(_request(req))


def gh_post(url, data):
    req = urllib.request.Request(
        url,
        data=json.dumps(data).encode(),
        headers={
            "Authorization": f"Bearer {GH_TOKEN}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    return json.loads(_request(req))


def gemini(payload):
    req = urllib.request.Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent",
        data=json.dumps(payload).encode(),
        headers={
            "x-goog-api-key": GEMINI_KEY,
            "content-type": "application/json",
        },
        method="POST",
    )
    return json.loads(_request(req))


def clone_repo(repo):
    dest = os.path.join(WORK_DIR, repo)
    shutil.rmtree(dest, ignore_errors=True)
    url = f"https://x-access-token:{GH_TOKEN}@github.com/{OWNER}/{repo}.git"
    subprocess.run(
        ["git", "clone", "--depth", "1", url, dest],
        check=True,
        capture_output=True,
        text=True,
    )
    return dest


def collect_files(repo_dir):
    files = []
    for root, dirs, names in os.walk(repo_dir):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        rel_root = os.path.relpath(root, repo_dir)
        for name in names:
            if name in SKIP_FILES:
                continue
            rel = os.path.join(rel_root, name) if rel_root != "." else name
            ext = os.path.splitext(name)[1].lower()
            if ext in INCLUDE_EXTS or name in INCLUDE_JSON or name == "Dockerfile":
                if os.path.getsize(os.path.join(root, name)) <= MAX_FILE_CHARS * 2:
                    files.append((rel, 0))
    files.sort(key=lambda f: (PRIORITY_DIR not in f[0], f[0]))
    return files


def build_context(repo_dir, files):
    parts = []
    total = 0
    for rel, _ in files:
        if total >= BUDGET_PER_REPO:
            break
        with open(os.path.join(repo_dir, rel), "r", encoding="utf-8", errors="replace") as f:
            code = f.read()
        if len(code) > MAX_FILE_CHARS:
            code = code[:MAX_FILE_CHARS]
            cut = code.rfind("\n")
            if cut > 0:
                code = code[:cut]
            code += "\n### TRUNCATED FOR REVIEW ###"
        parts.append({"file": rel, "code": code})
        total += len(code)
    return parts


def code_review(repo, context):
    payload = {
        "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": [
            {
                "role": "user",
                "parts": [
                    {
                        "text": json.dumps(
                            {"repository": repo, "files": context}, indent=1
                        )
                    }
                ],
            }
        ],
        "generationConfig": {
            "maxOutputTokens": 6000,
            "responseMimeType": "application/json",
            "responseSchema": RESPONSE_SCHEMA,
        },
    }
    findings = _review_call(payload)
    if not findings:
        payload["contents"][0]["parts"][0]["text"] = (
            payload["contents"][0]["parts"][0]["text"]
            + "\n\nYou returned no findings. Re-examine the code carefully and report "
            "any genuine defects, bugs, or security issues you find. It is acceptable "
            "to report several findings."
        )
        findings = _review_call(payload)
    return findings


def _review_call(payload):
    resp = gemini(payload)
    candidates = resp.get("candidates") or []
    if not candidates:
        raise RuntimeError("Gemini returned no candidates: " + json.dumps(resp)[:300])
    parts = candidates[0].get("content", {}).get("parts") or []
    text = "".join(p.get("text", "") for p in parts)
    return parse_findings(text)


def parse_findings(text):
    try:
        return json.loads(text).get("findings", [])
    except (ValueError, AttributeError):
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0)).get("findings", [])
            except (ValueError, AttributeError):
                return []
        return []


def open_issue_bodies(repo):
    issues = gh_get(
        f"https://api.github.com/repos/{OWNER}/{repo}/issues?state=open&per_page=100"
    )
    seen = []
    for it in issues:
        if "pull_request" in it:
            continue
        detail = gh_get(f"https://api.github.com/repos/{OWNER}/{repo}/issues/{it['number']}")
        seen.append((detail.get("title", ""), detail.get("body", "") or ""))
    return seen


def ensure_labels(repo):
    for label in (LABEL_AI, LABEL_GEN):
        try:
            gh_post(
                f"https://api.github.com/repos/{OWNER}/{repo}/labels",
                {"name": label, "description": "Applied by the automated AI code review"},
            )
        except RuntimeError as e:
            if "already_exists" not in str(e):
                raise


def fingerprint(repo, finding):
    raw = f"{repo}|{finding.get('file', '')}|{finding.get('location', '')}".lower()
    return hashlib.sha256(raw.encode()).hexdigest()[:12]


def create_issue(repo, finding, fp):
    body = (
        f"<!-- ai-review-fp: {fp} -->\n\n"
        f"**File:** `{finding.get('file', '')}`\n"
        f"**Location:** {finding.get('location', '')}\n"
        f"**Severity:** {finding.get('severity', '')}\n\n"
        f"{finding.get('description', '')}\n\n"
        f"**Suggested fix:**\n{finding.get('fix', '')}\n\n"
        "---\n_Generated automatically by the daily AI code review._"
    )
    created = gh_post(
        f"https://api.github.com/repos/{OWNER}/{repo}/issues",
        {
            "title": finding.get("title", "")[:120],
            "body": body,
            "labels": [LABEL_AI, LABEL_GEN],
        },
    )
    number = created.get("number")
    return number, created.get("html_url", f"https://github.com/{OWNER}/{repo}/issues/{number}")


def target_repos():
    if TARGET_REPOS:
        return TARGET_REPOS
    with open("repo_badges.json") as f:
        return json.load(f)["repos"]


def main():
    if not GH_TOKEN:
        sys.exit("GH_TOKEN not set")
    if not GEMINI_KEY:
        sys.exit("GEMINI_API_KEY not set")

    repos = target_repos()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    created = []
    dry_created = []
    errors = []

    for repo in repos:
        print(f"Reviewing {repo}...")
        try:
            repo_dir = clone_repo(repo)
            files = collect_files(repo_dir)
            context = build_context(repo_dir, files)
            if not context:
                print(f"  {repo}: no reviewable files")
                continue
            findings = code_review(repo, context)[:MAX_FINDINGS]
            existing = open_issue_bodies(repo)
            seen_fps = set()
            seen_titles = set()
            for title, body in existing:
                seen_titles.add(title.strip().lower())
                match = re.search(r"ai-review-fp: ([0-9a-f]{12})", body)
                if match:
                    seen_fps.add(match.group(1))

            if not DRY_RUN:
                ensure_labels(repo)

            new_count = 0
            for finding in findings:
                fp = fingerprint(repo, finding)
                title = (finding.get("title") or "").strip()
                if not title:
                    continue
                if fp in seen_fps or title.lower() in seen_titles:
                    continue
                if DRY_RUN:
                    dry_created.append((repo, title, finding))
                    new_count += 1
                    continue
                number, url = create_issue(repo, finding, fp)
                created.append((repo, number, title, url))
                new_count += 1
                seen_fps.add(fp)
                seen_titles.add(title.lower())
            print(f"  {repo}: {len(findings)} finding(s), {new_count} new")
        except Exception as e:
            errors.append(f"{repo}: {e}")
            print(f"  {repo}: ERROR {e}")

    lines = []
    if created:
        lines.append("# New AI review issues")
        for repo, number, title, url in created:
            lines.append(f"- [{repo} #{number}]({url}) - {title}")
    if dry_created:
        lines.append("# Dry-run findings (not filed)")
        for repo, title, finding in dry_created:
            lines.append(
                f"- {repo}: {title} [`{finding.get('file')}` {finding.get('location')}]"
            )
    if errors:
        lines.append("# Errors")
        lines.extend(f"- {e}" for e in errors)

    with open("ai_review_report.md", "w") as f:
        f.write(f"# AI Code Review - {now}\n\n" + "\n".join(lines) + "\n")

    if created:
        print(f"Filed {len(created)} new issue(s)")
    elif not DRY_RUN and not created:
        print("No new findings")

    print(f"Done. Created {len(created)} issue(s), dry-run {len(dry_created)}, errors {len(errors)}")


if __name__ == "__main__":
    main()
