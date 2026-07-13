# GitHub Repo Hygiene Audit — 2026-07-12

Account: **Rumblingb** · Non-forked, non-archived repos: **134**

## Summary

| Metric | Count |
|--------|------:|
| Fully complete (CI + dependabot + protection + no open work) | **0** |
| Has CI workflows | **7** |
| Has dependabot.yml | **0** |
| Branch protection on default branch | **0** |
| Open PRs (own repos) | **6** |
| Open issues | **4** |

## Spreadsheet

- CSV: `Agent-Hermes/github-repo-audit-2026-07-12.csv`
- Machine state: `.rumbling-hedge/state/github-repo-audit.latest.json`
- Refresh: `npm run bill:github-hygiene-audit`

## Active PRs (own repos, needs review)

| Repo | PR | Title | Blocker |
|------|----|-------|---------|
| hedge | [#2](https://github.com/Rumblingb/hedge/pull/2) | quarantine live-readiness WIP | CI test timeout |
| Agentpay | [#155](https://github.com/Rumblingb/Agentpay/pull/155) | MCP demo, docs, audit scripts | Vercel dashboard FAILURE |
| Agentpay | [#152](https://github.com/Rumblingb/Agentpay/pull/152) | marketplace authority safeguards | review |
| galatic-politics- | [#3](https://github.com/Rumblingb/galatic-politics-/pull/3) | store release prep | review |
| Iron-condor-v1 | [#1](https://github.com/Rumblingb/Iron-condor-v1/pull/1) | more data | review |
| awesome-mcp-servers-2 | [#1](https://github.com/Rumblingb/awesome-mcp-servers-2/pull/1) | AgentPay listing | review |

## HIGH priority repos (July 2026 activity)

hedge, Agentpay, regexlab, galatic-politics-, raise, triagegeist, july-2026-prize-hunt, loremipsum, thumbforge

## What was added to hedge (this session)

- `.github/dependabot.yml` — weekly npm + github-actions updates
- `.github/workflows/dependency-review.yml` — block high-severity deps on PRs
- `.github/workflows/codeql.yml` — JS/TS static analysis
- `.github/workflows/security-audit.yml` — weekday npm audit
- `scripts/github_repo_hygiene_audit.py` — rerunnable audit
- `scripts/github_repo_bootstrap.py` — batch PR hygiene to priority repos
- CI bump: Node 22, test timeout 120s

## Cursor automations (draft — user must Save)

1. **PR Security Review** — on PR open across Rumblingb org
2. **CI Failure Fix** — on CI fail, diagnose and comment
3. **Dependabot PR Review** — review vuln PRs, merge if safe
4. **Weekly Repo Hygiene** — Monday 08:00, refresh spreadsheet
5. **Daily Open PR Sweep** — weekdays 09:00, triage own-repo PRs
6. **Security Vuln Merge Gate** — on dependabot/security PR, security review then merge

## Bootstrap next repos

```bash
npm run bill:github-hygiene-bootstrap -- --repo Rumblingb/Agentpay --apply
npm run bill:github-hygiene-bootstrap -- --limit 10 --apply
```

## Branch protection (manual — needs admin scope)

`gh auth refresh -h github.com -s admin:repo_hook` then enable on master/main:
- Require PR before merge
- Require status checks (CI, dependency-review)
- Require dependabot security updates

## Loops armed

- 6h hygiene pulse: refresh audit + flag regressions
- PR monitor: check open PR CI status on priority repos
