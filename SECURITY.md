# Security Policy

Portfolio Advisor is currently a self-hosted alpha. It is intended for trusted local or private
network use, not untrusted public multi-user internet exposure.

## Supported Versions

Security fixes target the latest commit on the default branch until formal releases exist.

## Reporting A Vulnerability

Please open a private security advisory on GitHub if the repository supports it. If private
advisories are unavailable, open an issue with a minimal description and avoid posting exploit
details publicly.

Include:

- Affected version or commit
- Reproduction steps
- Expected impact
- Any relevant logs with secrets removed

## Security Notes

- The app does not include authentication or authorization.
- Review sessions are stored in server memory and are not durable records.
- Saved reviews in the UI are stored in the user's browser.
- API keys should be supplied through environment variables or `.env`, never committed.
- Third-party model, market-data, and news providers may receive prompts, portfolio inputs, or
  search queries depending on your configuration.

Add authentication, network controls, secret management, and persistence policies before exposing
the app to untrusted users.
