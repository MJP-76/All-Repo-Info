# All Repo Info

Central config for badges and support-me sections across all repos.

**Documentation:** [https://MJP-76.github.io/All-Repo-Info/](https://MJP-76.github.io/All-Repo-Info/)

## Badge Matrix

Edit the table below to enable/disable badges per repo, then run sync.

| Repo | Last Worked | Type | Version | HA | HACS | HACS Val | Hassfest | CI | Release | Built w/AI |
|------|:-----------:|:----:|:-------:|:--:|:----:|:--------:|:--------:|:--:|:-------:|:----------:|
| ha-dual-battery-control | 27/07/2026 | source | 0.1.29 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| DerrilWaterSolarPark | 27/07/2026 | source | 1.0.0 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| GithubConfigSync | 27/07/2026 | source | 1.4.1 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| GithubConfigSync-dev | 27/07/2026 | source |  | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| GraigFathaWindFarm | 27/07/2026 | source | 1.0.4 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| ha-ethex | 27/07/2026 | source | 0.1.3 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| KirkHillWindFarm | 27/07/2026 | source | 4.6.30 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |

> **Last Worked** = date of most recent commit. **Version** = from `manifest.json` or `VERSION` file. These are auto-updated by the sync script.

## How to Sync

### Option 1: GitHub Action (Recommended)

<a href="https://github.com/MJP-76/All-Repo-Info/actions/workflows/sync.yml" target="_blank"><img src="https://img.shields.io/badge/Run%20Sync-Click%20Here-blue?style=for-the-badge&logo=githubactions&logoColor=white" alt="Run Sync"></a>

### Option 2: Local Script

```bash
git clone https://github.com/MJP-76/All-Repo-Info.git
cd All-Repo-Info
python3 sync_repos.py --apply
```

## Files

- `repo_badges.json` — badge definitions, support-me config
- `sync_repos.py` — reads the badge matrix table and patches all repos
- `.github/workflows/sync.yml` — GitHub Action for manual trigger

[badge-run-sync]: https://img.shields.io/badge/Run%20Sync-Click%20Here-blue?style=for-the-badge&logo=githubactions&logoColor=white
[workflow-sync]: https://github.com/MJP-76/All-Repo-Info/actions/workflows/sync.yml
