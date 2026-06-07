# Security

## Reporting a vulnerability

Please report security issues privately via GitHub's **"Report a vulnerability"**
flow (Security → Advisories) on this repository, or email security@brokenbots.net.
Do not open a public issue for an undisclosed vulnerability.

## Supply-chain controls

This is a Python library (consumed by Criteria adapters), so it ships no binary.
Dependency hygiene is enforced in CI and documented in
[docs/dependency-policy.md](docs/dependency-policy.md):

- **`osv-scan`** — osv-scanner (pinned) runs on every PR/push as a **blocking**
  gate; no shipping known vulnerabilities. Exceptions are documented + dated in
  [`osv-scanner.toml`](osv-scanner.toml).
- **`deps-report`** — non-blocking freshness report (`uv pip list --outdated`).
- **7-day cooldown** on new releases (security fixes exempt); no automated update
  bot (small dependency surface — see the policy).

Reproduce the vulnerability gate locally with `make vuln-scan` (requires
osv-scanner on PATH).
