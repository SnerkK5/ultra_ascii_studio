# Security Policy

## Overview

**ultra_ascii_studio** is an application for converting images, GIFs, and videos into ASCII art.  
We take security seriously and appreciate responsible disclosure of vulnerabilities.

This document explains how to report security issues and how they will be handled.

---

## Supported Versions

Security updates are provided only for actively maintained versions of the project.

| Version | Supported |
|----------|------------|
| main (latest commit) | ✅ |
| Latest release | ✅ |
| Older releases | ❌ |

If you are using an outdated version, please upgrade before reporting a vulnerability.

---

## Reporting a Vulnerability

⚠️ **Please do NOT report security vulnerabilities through public GitHub Issues.**

Instead, use one of the following methods:

### Preferred Method: GitHub Security Advisories

1. Open the repository on GitHub.
2. Navigate to **Security → Advisories**.
3. Submit a private vulnerability report.

This allows the issue to be discussed and resolved before public disclosure.

### Alternative Contact

If GitHub Security Advisories are unavailable, please contact the repository maintainer directly (if contact information is provided in the repository profile).

---

## What to Include in Your Report

To help us investigate and resolve the issue efficiently, please include:

- The type of vulnerability (e.g., input validation issue, crash, dependency vulnerability, etc.)
- The affected version or commit hash
- Clear, step-by-step reproduction instructions
- A proof-of-concept (PoC), if applicable
- An assessment of potential impact

Providing detailed information will significantly speed up the resolution process.

---

## Response Process

1. We aim to acknowledge receipt of the report within **48 hours**.
2. The vulnerability will be reviewed and assessed.
3. A fix will be developed and tested.
4. A security patch or new release will be published.
5. If appropriate, a public security advisory will be issued.

Response times may vary depending on the severity and complexity of the issue.

---

## Security Best Practices

### For Contributors

- Keep dependencies up to date.
- Do not commit secrets (API keys, tokens, credentials).
- Validate and sanitize user inputs.
- Follow secure coding practices.

### For Users

- Download releases only from official sources.
- Verify the integrity of releases when possible.
- Run the application in a controlled environment when processing untrusted files.

---

## Responsible Disclosure

We kindly request that you:

- Do not publicly disclose vulnerabilities before they are fixed.
- Allow reasonable time for remediation.
- Act in good faith when testing the project.

We sincerely appreciate security researchers and contributors who help improve the safety of this project.

---

Thank you for helping make **ultra_ascii_studio** more secure.
