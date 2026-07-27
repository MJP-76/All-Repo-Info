#!/usr/bin/env python3
"""Sync badges and support-me section across all repos from a single config.

Usage:
    python sync_badges.py                  # preview all repos
    python sync_badges.py --apply          # commit and push changes
    python sync_badges.py --repo ha-ethex  # preview one repo
    python sync_badges.py --repo ha-ethex --apply
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
CONFIG_PATH = SCRIPT_DIR / "repo_badges.json"
DEFAULT_REPOS_DIR = SCRIPT_DIR.parent


def load_config():
    with open(CONFIG_PATH) as f:
        return json.load(f)


def badge_ref_name(name):
    return name.replace("_", "-")


def build_badge_block(config, owner, repo):
    lines = []
    for name in config["badge_order"]:
        badge = config["badges"][name]
        display = badge.get("display", name.replace("_", " ").title())
        ref = badge_ref_name(name)

        if "workflow" in badge:
            lines.append(f"[![{display}][badge-{ref}]][workflow-{ref}]")
        elif "link" in badge:
            link = badge["link"]
            # Use the link value as the ref name if it's a simple name (not a URL)
            if not link.startswith("http"):
                link_ref = link
            else:
                link_ref = ref
            lines.append(f"[![{display}][badge-{ref}]][{link_ref}]")
        else:
            lines.append(f"![{display}][badge-{ref}]")
    return "\n".join(lines)


def build_badge_refs(config, owner, repo):
    lines = []
    for name in config["badge_order"]:
        badge = config["badges"][name]
        ref = badge_ref_name(name)
        image = badge["image"].replace("{owner}", owner).replace("{repo}", repo)
        lines.append(f"[badge-{ref}]: {image}")
        if "workflow" in badge:
            link = f"https://github.com/{owner}/{repo}/actions/workflows/{badge['workflow']}"
            lines.append(f"[workflow-{ref}]: {link}")
        elif "link" in badge:
            link = badge["link"]
            if link == "releases":
                link_url = f"https://github.com/{owner}/{repo}/releases"
            elif link.startswith("http"):
                link_url = link
            else:
                link_url = link
            # Use the link value as the ref name if it's a simple name
            link_ref = link if not link.startswith("http") else ref
            lines.append(f"[{link_ref}]: {link_url}")
    return "\n".join(lines)


def build_support_me(config):
    sm = config["support_me"]
    lines = ["## Support me\n", sm["text"], ""]
    for btn in sm["buttons"]:
        lines.append(f"[![{btn['label']}]({btn['image']})]({btn['link']})")
    lines.append("")  # trailing blank before next section
    return "\n".join(lines)


def patch_readme(original, config, owner, repo):
    lines = original.split("\n")

    # --- 1. Replace badge block (lines after # Title, before first non-badge content) ---
    title_idx = None
    badge_start = None
    badge_end = None
    for i, line in enumerate(lines):
        s = line.strip()
        if s.startswith("# ") and title_idx is None:
            title_idx = i
            continue
        if title_idx is None:
            continue
        if badge_start is None:
            if s.startswith("[![") or s.startswith("!["):
                badge_start = i
                badge_end = i
            elif s == "":
                continue
            else:
                break
        else:
            if s.startswith("[![") or s.startswith("!["):
                badge_end = i
            elif s == "":
                badge_end = i  # allow trailing blank
            else:
                break

    if badge_start is not None:
        new_block = build_badge_block(config, owner, repo)
        # Preserve trailing blank line after badge block
        had_trailing_blank = lines[badge_end].strip() == ""
        lines[badge_start:badge_end + 1] = new_block.split("\n")
        if had_trailing_blank:
            # Insert blank line after the last badge line
            badge_lines = new_block.split("\n")
            insert_at = badge_start + len(badge_lines)
            lines.insert(insert_at, "")

    # --- 2. Replace support me section ---
    sm_start = None
    sm_end = None
    for i, line in enumerate(lines):
        if line.strip() == "## Support me":
            sm_start = i
        elif sm_start is not None and line.strip().startswith("## "):
            sm_end = i
            break
    if sm_start is not None and sm_end is None:
        sm_end = len(lines)
    if sm_start is not None:
        new_sm = build_support_me(config)
        lines[sm_start:sm_end] = new_sm.split("\n")

    # --- 3. Replace ref block at end of file ---
    # Find contiguous block of [ref]: url lines at end
    ref_end = len(lines) - 1
    while ref_end >= 0 and lines[ref_end].strip() == "":
        ref_end -= 1
    ref_start = ref_end
    while ref_start >= 0:
        s = lines[ref_start].strip()
        if s.startswith("[") and "]: " in s:
            ref_start -= 1
        else:
            break
    ref_start += 1

    if ref_start <= ref_end:
        # Preserve blank line before ref block if it existed
        had_blank_before = ref_start > 0 and lines[ref_start - 1].strip() == ""
        new_refs = build_badge_refs(config, owner, repo)
        lines[ref_start:ref_end + 1] = new_refs.split("\n")
        if had_blank_before and ref_start > 0 and lines[ref_start - 1].strip() != "":
            lines.insert(ref_start, "")

    return "\n".join(lines)


def git_cmd(repo_path, *args):
    result = subprocess.run(
        ["git"] + list(args), cwd=repo_path, capture_output=True, text=True,
    )
    return result.stdout.strip(), result.returncode


def process_repo(config, repo_name, apply=False, repos_dir=None):
    owner = config["owner"]
    repo_path = repos_dir / repo_name
    if not repo_path.exists():
        for base in [Path("/data"), Path("/data/.cache/opencode-tmp")]:
            candidate = base / repo_name
            if candidate.exists():
                repo_path = candidate
                break
    if not repo_path.exists():
        print(f"  SKIP: {repo_path} not found")
        return False

    readme = None
    for name in ["README.md", "readme.md"]:
        p = repo_path / name
        if p.exists():
            readme = p
            break
    if not readme:
        print(f"  SKIP: no README in {repo_path}")
        return False

    original = readme.read_text()
    patched = patch_readme(original, config, owner, repo_name)

    if original == patched:
        print(f"  OK: {repo_name} already up to date")
        return False

    orig_lines = original.split("\n")
    patch_lines = patched.split("\n")
    changes = sum(1 for o, p in zip(orig_lines, patch_lines) if o != p)
    changes += abs(len(orig_lines) - len(patch_lines))

    print(f"  CHANGED: {repo_name} ({changes} lines differ)")

    if apply:
        readme.write_text(patched)
        git_cmd(repo_path, "add", "README.md")
        git_cmd(repo_path, "commit", "-m", "docs: sync badges and support-me from central config")
        for remote in ["origin", "dev"]:
            for branch in ["main", "master"]:
                stdout, rc = git_cmd(repo_path, "push", remote, branch)
                if rc == 0:
                    break
        print(f"  PUSHED: {repo_name}")
        return True

    return True


def main():
    parser = argparse.ArgumentParser(description="Sync badges across repos")
    parser.add_argument("--apply", action="store_true", help="Commit and push changes")
    parser.add_argument("--repo", help="Only process this repo")
    parser.add_argument("--repos-dir", type=Path, default=DEFAULT_REPOS_DIR)
    args = parser.parse_args()

    config = load_config()
    repos = [args.repo] if args.repo else config["repos"]

    changed = 0
    for repo in repos:
        print(f"\n{repo}:")
        if process_repo(config, repo, apply=args.apply, repos_dir=args.repos_dir):
            changed += 1

    print(f"\n{'Done' if args.apply else 'Preview'}: {changed} repo(s) {'updated' if args.apply else 'need updates'}")


if __name__ == "__main__":
    main()
