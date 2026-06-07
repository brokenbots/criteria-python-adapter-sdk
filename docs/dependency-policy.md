# Dependency-freshness & supply-chain policy

This SDK follows the same two locked mandates as the
[Criteria monorepo](https://github.com/brokenbots/criteria/blob/main/docs/dependency-policy.md).
Each repo owns its own copy; this file is the local authority. It applies to the
Python dependencies (`pyproject.toml` / `uv.lock`) and the GitHub Actions used in
CI.

## 1. Stay current — latest major.minor

Be on the **latest major and minor** of every dependency. Patch versions roll up
freely *within* the cooldown rule below. The only reason to pin **below** latest
is a concrete one: a newer version has a **known security vulnerability** that
affects us, or a **bug we are actually hit by**. Any such pin is a documented,
dated exception (see below).

## 2. Defend against supply-chain attacks — 7-day cooldown

Do **not** adopt any release **newer than 7 days** unless it fixes a known
security issue or a specific bug we're hit by. **Security updates bypass the
cooldown.**

## How freshness & vulnerabilities are tracked — no update bot

This repo runs **no automated dependency-update bot**. The dependency surface is
small, so freshness is managed by review against the tooling below:

| Command | Tool | Answers |
| --- | --- | --- |
| `make vuln-scan` | [`osv-scanner`](https://github.com/google/osv-scanner) | Which deps carry a known advisory (reads `uv.lock`). **CI gate (WS49).** |
| `uv pip list --outdated` | `uv` | Which deps are behind their latest version. |

- **`osv-scan`** runs in CI on every PR/push (pinned `google/osv-scanner-action`)
  and is a **required, blocking** check.
- **`deps-report`** runs `uv pip list --outdated` non-blocking and posts the
  result to the job summary.

Applying upgrades (honor the 7-day cooldown unless it's a security/bug fix):

```bash
uv lock --upgrade-package <pkg>   # bump one dependency
uv lock --upgrade                 # refresh all within constraints
```

After any upgrade: `uv sync`, `make test`, `make vuln-scan`.

## Holding a dependency below latest

Record any pin below latest as a dated exception (mirrors the `osv-scanner.toml`
"documented + dated" convention) and constrain it in `pyproject.toml`.

| Dependency | Held at | Reason (advisory / bug) | Review by |
| --- | --- | --- | --- |
| _none_ | | | |

On the review date the exception must be cleared or re-justified.
