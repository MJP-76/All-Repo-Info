#!/usr/bin/env python3
"""Sync badges and support-me section across all repos.

Reads the badge matrix table from README.md to determine which badges each repo should have.
Auto-updates Last Worked, Status, and Version columns from repo data.

Usage:
    python sync_repos.py                  # preview all repos
    python sync_repos.py --apply          # commit and push changes
    python sync_repos.py --repo ha-ethex  # preview one repo
    python sync_repos.py --repo ha-ethex --apply
"""
import argparse
import json
import os
import re
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
CONFIG_PATH = SCRIPT_DIR / "repo_badges.json"
README_PATH = SCRIPT_DIR / "README.md"
DEFAULT_REPOS_DIR = SCRIPT_DIR.parent


def get_all_repos(owner, token=None):
    """Fetch all repos for owner via GitHub API (public, private, forks, archived)."""
    repos = []
    page = 1
    while True:
        url = f"https://api.github.com/user/repos?per_page=100&page={page}&type=all"
        headers = {"Accept": "application/vnd.github+json"}
        if token:
            headers["Authorization"] = f"token {token}"
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req) as resp:
                data = json.loads(resp.read())
        except Exception as e:
            print(f"WARNING: GitHub API error: {e}")
            break
        if not data:
            break
        for r in data:
            if r["owner"]["login"].lower() == owner.lower():
                repos.append({
                    "name": r["name"],
                    "fork": r["fork"],
                    "archived": r["archived"],
                    "private": r["private"],
                })
        page += 1
    return repos

# Badge columns only (not metadata columns)
BADGE_COLUMNS = [
    "home_assistant",   # HA
    "hacs",             # HACS
    "hacs_validation",  # HACS Val
    "hassfest",         # Hassfest
    "ci",               # CI
    "release",          # Release
    "built_with_ai",    # Built w/AI
]


def load_config():
    with open(CONFIG_PATH) as f:
        return json.load(f)


def parse_badge_matrix(readme_text):
    """Parse the badge matrix table from README.md.
    
    Returns dict: {repo_name: {"badges": {badge_name: bool}, "last_worked": str, "status": str, "version": str}}
    """
    repos = {}
    in_table = False
    
    for line in readme_text.split("\n"):
        stripped = line.strip()
        
        # Detect table start
        if stripped.startswith("| Repo |"):
            in_table = True
            continue
        
        # Skip separator line
        if in_table and stripped.startswith("|------"):
            continue
        
        # Parse table rows
        if in_table and stripped.startswith("|"):
            cells = [c.strip() for c in stripped.split("|")]
            cells = cells[1:-1]  # remove empty first/last from leading/trailing |
            
            if len(cells) < 2:
                continue
            
            repo_name = cells[0].strip()
            if not repo_name or repo_name == "Repo":
                continue
            
            # Metadata columns: Last Worked (1), Status (2), Version (3)
            last_worked = cells[1].strip() if len(cells) > 1 else "—"
            status = cells[2].strip() if len(cells) > 2 else "experimental"
            version = cells[3].strip() if len(cells) > 3 else "—"
            
            # Badge columns start at index 4
            badges = {}
            for i, badge_name in enumerate(BADGE_COLUMNS):
                col_idx = i + 4
                if col_idx < len(cells):
                    cell = cells[col_idx].strip()
                    badges[badge_name] = cell in ("✅", "☑️")
                else:
                    badges[badge_name] = False
            
            repos[repo_name] = {
                "badges": badges,
                "last_worked": last_worked,
                "status": status,
                "version": version,
            }
        
        elif in_table and not stripped.startswith("|"):
            break
    
    return repos


def badge_ref_name(name):
    return name.replace("_", "-")


def get_last_commit_date(repo_path):
    """Get the date of the most recent commit."""
    result = subprocess.run(
        ["git", "log", "-1", "--format=%ci"],
        cwd=repo_path, capture_output=True, text=True,
    )
    if result.returncode == 0 and result.stdout.strip():
        try:
            dt = datetime.fromisoformat(result.stdout.strip())
            return dt.strftime("%d/%m/%Y")
        except ValueError:
            pass
    return "—"


def get_version(repo_path):
    """Get version from manifest.json or VERSION file."""
    # Try manifest.json first
    for domain_dir in (repo_path / "custom_components").iterdir() if (repo_path / "custom_components").exists() else []:
        manifest = domain_dir / "manifest.json"
        if manifest.exists():
            try:
                data = json.loads(manifest.read_text())
                return data.get("version", "—")
            except (json.JSONDecodeError, KeyError):
                pass
    
    # Try VERSION file
    version_file = repo_path / "VERSION"
    if version_file.exists():
        return version_file.read_text().strip()
    
    # Try config.yaml (for add-ons)
    config_yaml = repo_path / "config.yaml"
    if config_yaml.exists():
        try:
            import yaml
            data = yaml.safe_load(config_yaml.read_text())
            return data.get("version", "—")
        except Exception:
            pass
    
    return "—"


def update_readme_table(readme_text, repo_data):
    """Update the badge matrix table in README with fresh metadata."""
    lines = readme_text.split("\n")
    new_lines = []
    in_table = False
    
    for line in lines:
        stripped = line.strip()
        
        if stripped.startswith("| Repo |"):
            in_table = True
            new_lines.append(line)
            continue
        
        if in_table and stripped.startswith("|------"):
            new_lines.append(line)
            continue
        
        if in_table and stripped.startswith("|"):
            cells = [c.strip() for c in stripped.split("|")]
            cells = cells[1:-1]
            
            repo_name = cells[0].strip()
            if repo_name in repo_data:
                data = repo_data[repo_name]
                # Update metadata columns (indices 1-3), keep badge columns (4+) as-is
                cells[1] = data["last_worked"]
                cells[2] = data["status"]
                cells[3] = data["version"]
                new_line = "| " + " | ".join(cells) + " |"
                new_lines.append(new_line)
            else:
                new_lines.append(line)
            continue
        
        if in_table and not stripped.startswith("|"):
            in_table = False
        
        new_lines.append(line)
    
    return "\n".join(new_lines)


def update_badge_matrix_table(readme_text, badge_matrix):
    """Add new repos to the badge matrix table in README, sorted alphabetically."""
    lines = readme_text.split("\n")
    result = []
    in_table = False
    sep_idx = None
    existing_repos = {}
    found_table_end = False

    for line in lines:
        stripped = line.strip()

        if not found_table_end and stripped.startswith("| Repo |"):
            in_table = True
            result.append(line)
            continue

        if in_table and stripped.startswith("|------"):
            sep_idx = len(result)
            result.append(line)
            continue

        if in_table and stripped.startswith("|"):
            cells = [c.strip() for c in stripped.split("|")]
            cells = cells[1:-1]
            repo_name = cells[0].strip()
            if repo_name:
                existing_repos[repo_name] = cells
            continue

        if in_table and not stripped.startswith("|"):
            in_table = False
            found_table_end = True

        result.append(line)

    # Merge: existing repos keep their badge columns, new repos get defaults
    all_repos = set(existing_repos.keys()) | set(badge_matrix.keys())
    all_repos.discard("All-Repo-Info")
    sorted_repos = sorted(all_repos, key=str.lower)

    if sep_idx is not None:
        # Remove existing rows from result (everything after sep_idx until table ends)
        # Rebuild: header + sep + sorted rows + rest
        header = result[sep_idx - 1]  # "| Repo | ..."
        sep = result[sep_idx]         # "|------|..."
        rest = result[sep_idx + 1:]   # everything after the table

        rows = []
        for repo_name in sorted_repos:
            if repo_name in existing_repos:
                cells = existing_repos[repo_name]
                # Update metadata from badge_matrix if available
                if repo_name in badge_matrix:
                    info = badge_matrix[repo_name]
                    cells[1] = info.get("last_worked", cells[1])
                    cells[2] = info.get("status", cells[2])
                    cells[3] = info.get("version", cells[3])
                rows.append("| " + " | ".join(cells) + " |")
            elif repo_name in badge_matrix:
                info = badge_matrix[repo_name]
                status = info.get("status", "experimental")
                version = info.get("version", "—")
                last_worked = info.get("last_worked", "—")
                badge_cells = " | ".join(["❌"] * len(BADGE_COLUMNS))
                rows.append(f"| {repo_name} | {last_worked} | {status} | {version} | {badge_cells} |")

        result = result[:sep_idx - 1] + [header, sep] + rows + rest

    return "\n".join(result)


def build_badge_block(config, enabled_badges, owner, repo):
    lines = []
    docs = config["badges"].get("documentation")
    if docs:
        display = docs.get("display", "Documentation")
        lines.append(f"[![{display}][badge-docs]][docs]")
    for name in BADGE_COLUMNS:
        if not enabled_badges.get(name, False):
            continue
        badge = config["badges"][name]
        display = badge.get("display", name.replace("_", " ").title())
        ref = badge_ref_name(name)

        if "workflow" in badge:
            lines.append(f"[![{display}][badge-{ref}]][workflow-{ref}]")
        elif "link" in badge:
            link = badge["link"]
            if not link.startswith("http"):
                link_ref = link
            else:
                link_ref = ref
            lines.append(f"[![{display}][badge-{ref}]][{link_ref}]")
        else:
            lines.append(f"![{display}][badge-{ref}]")
    return "\n".join(lines)


def build_badge_refs(config, enabled_badges, owner, repo):
    lines = []
    docs = config["badges"].get("documentation")
    if docs:
        image = docs["image"].replace("{owner}", owner).replace("{repo}", repo)
        link = docs["link"].replace("{owner}", owner).replace("{repo}", repo)
        lines.append(f"[badge-docs]: {image}")
        lines.append(f"[docs]: {link}")
    for name in BADGE_COLUMNS:
        if not enabled_badges.get(name, False):
            continue
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
            link_ref = link if not link.startswith("http") else ref
            lines.append(f"[{link_ref}]: {link_url}")
    return "\n".join(lines)


def build_support_me(config):
    sm = config["support_me"]
    lines = ["## Support me\n", sm["text"], ""]
    for btn in sm["buttons"]:
        lines.append(f"[![{btn['label']}]({btn['image']})]({btn['link']})")
    lines.append("")
    return "\n".join(lines)


def build_footer_sections(config):
    """Build the Contributing and License sections."""
    contributing = config.get("contributing", {})
    license_cfg = config.get("license", {})
    lines = [
        "## Contributing\n",
        contributing.get("text", "Contributions are welcome!"),
        "\n",
        f"## License\n",
        "",
        license_cfg.get("text", "MIT License — see [LICENSE](LICENSE) for the full text."),
        "",
    ]
    return "\n".join(lines)


def patch_readme(readme_text, config, enabled_badges, owner, repo):
    lines = readme_text.split("\n")

    # --- 1. Replace badge block ---
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
                badge_end = i
            else:
                break

    if badge_start is not None:
        new_block = build_badge_block(config, enabled_badges, owner, repo)
        had_trailing_blank = lines[badge_end].strip() == ""
        lines[badge_start:badge_end + 1] = new_block.split("\n")
        if had_trailing_blank:
            insert_at = badge_start + len(new_block.split("\n"))
            lines.insert(insert_at, "")
    elif title_idx is not None:
        new_block = build_badge_block(config, enabled_badges, owner, repo)
        insert_at = title_idx + 1
        lines.insert(insert_at, "")
        insert_at += 1
        for j, bl in enumerate(new_block.split("\n")):
            lines.insert(insert_at + j, bl)
        lines.insert(insert_at + len(new_block.split("\n")), "")

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

    # --- 3. Replace footer sections (Contributing + License) before ref block ---
    footer = build_footer_sections(config).split("\n")
    # Remove any existing Contributing/License sections anywhere in the doc
    filtered = []
    i = 0
    while i < len(lines):
        if lines[i].strip() in ("## Contributing", "## License"):
            i += 1
            while i < len(lines) and lines[i].strip() not in ("## Contributing", "## License") and not (lines[i].strip().startswith("[") and "]: " in lines[i].strip()):
                i += 1
            continue
        filtered.append(lines[i])
        i += 1
    lines = filtered

    # --- 4. Replace ref block at end ---
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

    new_refs = build_badge_refs(config, enabled_badges, owner, repo)
    if ref_start <= ref_end:
        # Replace existing ref block
        had_blank_before = ref_start > 0 and lines[ref_start - 1].strip() == ""
        lines[ref_start:ref_end + 1] = new_refs.split("\n")
        if had_blank_before and ref_start > 0 and lines[ref_start - 1].strip() != "":
            lines.insert(ref_start, "")
    else:
        # No existing refs — append at end
        last_non_blank = len(lines) - 1
        while last_non_blank >= 0 and lines[last_non_blank].strip() == "":
            last_non_blank -= 1
        insert_at = last_non_blank + 1
        lines.insert(insert_at, "")
        insert_at += 1
        for j, rl in enumerate(new_refs.split("\n")):
            lines.insert(insert_at + j, rl)

    return "\n".join(lines)


def git_cmd(repo_path, *args):
    result = subprocess.run(
        ["git"] + list(args), cwd=repo_path, capture_output=True, text=True,
    )
    return result.stdout.strip(), result.returncode


def process_repo(config, repo_name, enabled_badges, apply=False, repos_dir=None):
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
    patched = patch_readme(original, config, enabled_badges, owner, repo_name)

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
        git_cmd(repo_path, "commit", "-m", "docs: sync badges and support-me from All-Repo-Info")
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
    parser.add_argument("--update-table", action="store_true", help="Update README table with fresh metadata")
    parser.add_argument("--discover", action="store_true", help="Auto-discover repos via GitHub API and add to matrix")
    parser.add_argument("--github-token", default=os.environ.get("GITHUB_TOKEN"), help="GitHub token for API access")
    args = parser.parse_args()

    config = load_config()
    owner = config["owner"]

    # Read badge matrix from README
    if README_PATH.exists():
        readme = README_PATH.read_text()
        badge_matrix = parse_badge_matrix(readme)
    else:
        print(f"ERROR: {README_PATH} not found")
        sys.exit(1)

# Auto-discover repos via GitHub API
    if args.discover:
        print("Discovering repos via GitHub API...")
        all_repos = get_all_repos(owner, args.github_token)
        discovered_names = {r["name"] for r in all_repos}
        print(f"Found {len(all_repos)} repos")

        # Add new repos to badge matrix with empty badges
        for repo_info in all_repos:
            name = repo_info["name"]
            if repo_info["fork"]:
                print(f"  Skipped (fork): {name}")
                continue
            if name not in badge_matrix and name != "All-Repo-Info":
                badge_matrix[name] = {
                    "badges": {b: False for b in BADGE_COLUMNS},
                    "last_worked": "—",
                    "status": "archived" if repo_info["archived"] else "experimental",
                    "version": "—",
                }
                new_repos.append(name)
                print(f"  Added: {name}" + (" (archived)" if repo_info["archived"] else "") + (" (fork)" if repo_info["fork"] else ""))

        if new_repos:
            # Update README table with new repos
            readme = update_badge_matrix_table(readme, badge_matrix)
            README_PATH.write_text(readme)
            print(f"Added {len(new_repos)} new repos to README table")

            # Update repo_badges.json
            repos_json = config.get("repos", [])
            for name in sorted(badge_matrix.keys()):
                if name not in repos_json and name != "All-Repo-Info":
                    repos_json.append(name)
            config["repos"] = sorted(repos_json)
            CONFIG_PATH.write_text(json.dumps(config, indent=2) + "\n")
            print("Updated repo_badges.json")

            # Re-read for processing
            readme = README_PATH.read_text()
            badge_matrix = parse_badge_matrix(readme)

    # Collect fresh metadata from repos
    repo_metadata = {}
    for repo_name in badge_matrix:
        repo_path = find_repo(repo_name, args.repos_dir)
        if repo_path:
            repo_metadata[repo_name] = {
                "last_worked": get_last_commit_date(repo_path),
                "status": badge_matrix[repo_name]["status"],
                "version": get_version(repo_path),
            }
        else:
            repo_metadata[repo_name] = {
                "last_worked": badge_matrix[repo_name]["last_worked"],
                "status": badge_matrix[repo_name]["status"],
                "version": badge_matrix[repo_name]["version"],
            }

    # Update README table if requested
    if args.update_table:
        updated_readme = update_readme_table(readme, repo_metadata)
        if updated_readme != readme:
            README_PATH.write_text(updated_readme)
            print("Updated README table with fresh metadata")
            # Re-read for badge sync
            readme = updated_readme
            badge_matrix = parse_badge_matrix(readme)

    if args.repo:
        repos = [args.repo]
    else:
        repos = list(badge_matrix.keys())

    changed = 0
    for repo in repos:
        repo_info = badge_matrix.get(repo, {})
        enabled = repo_info.get("badges", {}) if isinstance(repo_info, dict) else repo_info
        status = repo_info.get("status", "experimental") if isinstance(repo_info, dict) else "experimental"
        if not enabled:
            print(f"\n{repo}:")
            print(f"  SKIP: not found in badge matrix")
            continue
        print(f"\n{repo}:")
        if process_repo(config, repo, enabled, apply=args.apply, repos_dir=args.repos_dir):
            changed += 1

    print(f"\n{'Done' if args.apply else 'Preview'}: {changed} repo(s) {'updated' if args.apply else 'need updates'}")


def find_repo(repo_name, repos_dir):
    """Find a repo directory."""
    repo_path = repos_dir / repo_name
    if repo_path.exists():
        return repo_path
    for base in [Path("/data"), Path("/data/.cache/opencode-tmp")]:
        candidate = base / repo_name
        if candidate.exists():
            return candidate
    return None


if __name__ == "__main__":
    main()
