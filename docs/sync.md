# How syncing works

One central config drives the badge and support-me sections in every
repository's README. Nothing is edited by hand across the repos — edit here,
then run the sync.

## Source of truth

- `repo_badges.json` — badge definitions, support-me buttons, and the list of
  repos to manage.
- `README.md` — the **badge matrix table** is read back by the sync script, so
  the table stays the editable view of which badges each repo has.
- `sync_repos.py` — the engine. It reads the matrix in `README.md` and patches
  each repo's README with:

  1. the badge block (the wired shield badges under the title),
  2. the **Support me** section,
  3. the Contributing/License footer,
  4. the link-reference block at the bottom of the file.

## Metadata columns

The sync script auto-updates three columns of the matrix from local repo data:

- **Last Worked** — date of the most recent `git` commit
  (`get_last_commit_date`).
- **Status** — from the matrix (e.g. `experimental`, `source`, `archived`).
- **Version** — from `custom_components/*/manifest.json`, a `VERSION` file, or
  an add-on `config.yaml` (`get_version`).

## Running it

### GitHub Action (recommended)

<a href="https://github.com/MJP-76/All-Repo-Info/actions/workflows/sync.yml"><img src="https://img.shields.io/badge/Run%20Sync-Click%20Here-blue?style=for-the-badge&logo=githubactions&logoColor=white" alt="Run Sync"></a>

### Locally

```bash
git clone https://github.com/MJP-76/All-Repo-Info.git
cd All-Repo-Info
python3 sync_repos.py             # preview only
python3 sync_repos.py --apply     # commit and push changes
```

### Options

| Flag | What it does |
|---|---|
| `--repo NAME` | Process only `NAME` |
| `--repo NAME --apply` | Commit and push that repo |
| `--update-table` | Refresh Last Worked/Status/Version in the matrix |
| `--discover` | Add new GitHub repos to the matrix automatically |
| `--repos-dir PATH` | Where local repo checkouts live |