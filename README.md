# All Repo Info

Central config for badges and support-me sections across all repos.

## Badge Matrix

Edit the table below to enable/disable badges per repo, then run sync.

| Repo | Last Worked | Status | Version | HA | HACS | HACS Val | Hassfest | CI | Release | Built w/AI |
|------|:-----------:|:------:|:-------:|:--:|:----:|:--------:|:--------:|:--:|:-------:|:----------:|
| GithubConfigSync | 2026-07-27 | experimental | 1.4.1 | ✅ | ✅ | ✅ | ✅ | ❌ | ✅ | ✅ |
| crossbatterychargeguard | 2026-07-27 | experimental | 0.1.29 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| ha-ethex | 2026-07-27 | experimental | 0.1.3 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| KirkHillWindFarm | 2026-07-27 | experimental | 4.6.30 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| GraigFathaWindFarm | 2026-07-27 | experimental | 1.0.4 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| DerrilWaterSolarPark | 2026-07-27 | experimental | 1.0.0 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |

> **Last Worked** = date of most recent commit. **Version** = from `manifest.json` or `VERSION` file. These are auto-updated by the sync script.

## How to Sync

### Option 1: GitHub Action (Recommended)

[![Run Sync][badge-run-sync]][workflow-sync]

### Option 2: Local Script

```bash
git clone https://github.com/MJP-76/All-Repo-Info.git
cd All-Repo-Info
python3 sync_badges.py --apply
```

## Files

- `repo_badges.json` — badge definitions, support-me config
- `sync_badges.py` — reads the badge matrix table and patches all repos
- `.github/workflows/sync.yml` — GitHub Action for manual trigger

[badge-run-sync]: https://img.shields.io/badge/Run%20Sync-Click%20Here-blue?style=for-the-badge&logo=githubactions&logoColor=white
[workflow-sync]: https://github.com/MJP-76/All-Repo-Info/actions/workflows/sync.yml
