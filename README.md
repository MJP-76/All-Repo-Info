# All Repo Info

Central config for badges and support-me sections across all repos.

## Badge Matrix

Edit the table below to enable/disable badges per repo, then run sync.

| Repo | HA | HACS | HACS Val | Hassfest | CI | Release | Status | Built w/AI |
|------|:--:|:----:|:--------:|:--------:|:--:|:-------:|:------:|:----------:|
| GithubConfigSync | ✅ | ✅ | ✅ | ✅ | ❌ | ✅ | ✅ | ✅ |
| crossbatterychargeguard | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| ha-ethex | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| KirkHillWindFarm | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| GraigFathaWindFarm | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| DerrilWaterSolarPark | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |

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
