# Security policy

## Reporting a vulnerability

Use the hosting platform's private security-advisory channel when available. If no private channel is configured, open a minimal issue asking maintainers to establish private contact; do not include exploit details, credentials, private provider responses or user data in that issue.

Include affected versions, impact, reproduction conditions and a proposed mitigation if known. Maintainers will acknowledge a complete report after a private channel is established; no response-time SLA is currently promised.

## Secrets and data

- Keep backend credentials in `.env` or the deployment secret manager.
- Never use `NEXT_PUBLIC_*` for secrets.
- Do not attach raw generation payloads or logs without redaction.
- Publish from tracked Git content, not a workspace archive containing ignored files.
