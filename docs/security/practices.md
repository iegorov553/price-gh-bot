# Security Practices

Protecting credentials and reducing attack surface is essential for operating Price GH Bot safely.

## Secrets Management
- Store `BOT_TOKEN`, `ADMIN_CHAT_ID`, and optional `GITHUB_TOKEN` in a secret manager or environment variables supplied by your platform.
- Rotate tokens after incidents, when staff changes, or at least quarterly.
- Never commit secrets to the repository. Use `.env` only for local development and add it to `.gitignore`.

## Least Privilege
- Restrict who knows the admin chat ID. Admin commands expose sensitive analytics and data exports.
- Limit file system permissions so the bot can only access its working directory and analytics storage.
- When running in containers, avoid root where possible and use read-only file systems with writable mounts for required paths.

## Transport Security
- Enforce HTTPS when running webhook mode. Validate that certificates are valid and renewed automatically.
- Keep outbound network policies open only to Telegram, eBay, Grailed, CBR API, and optional Redis hosts.

## Dependency Hygiene
- Update dependencies regularly with `poetry update` and rebuild Docker images to receive upstream security fixes.
- Run `poetry run bandit -c pyproject.toml -r app` and `poetry run pip-audit` before every deployment.
- Track security advisories for Playwright and Telegram libraries.
- Use hardened parsing libraries (`defusedxml` for XML, `bleach` for HTML sanitisation) instead of the Python standard library when processing untrusted data.

## Data Protection
- Analytics captures limited user information (user ID, username, URLs). Review compliance requirements for your jurisdiction.
- If you export analytics data, store it securely and remove it when no longer needed.
- Do not log full access tokens or personally identifiable information.

## Operational Hardening
- Configure log retention and alerting to detect anomalies (suspicious URLs, repeated errors).
- Guard access to backup locations that store `data/analytics.db`.
- For self-hosted Redis, enable authentication and TLS.
- Keep the webhook listener bound to `127.0.0.1` by default via `BOT_LISTEN_HOST`, and only expose `0.0.0.0` when an ingress proxy is in front of the bot.

## Incident Response
- Document how to rotate credentials, redeploy updated images, and recover from backups.
- Maintain runbooks for scraping layout changes and analytics anomalies.
- File a post-incident report in the repository (issues or docs) to share lessons learned.

Security is an ongoing process. Review this document after major releases or infrastructure changes.
