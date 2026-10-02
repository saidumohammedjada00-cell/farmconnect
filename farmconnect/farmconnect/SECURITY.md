# FarmConnect minimum security standard

Baseline: **OWASP Top 10:2025** (released November 2025; it replaces the 2021 list).
Release rule: every row marked **Required** must be Done before the app goes live.

| OWASP 2025 | Control | Required | Status |
|---|---|---|---|
| **A01 Broken Access Control** (SSRF now sits here) | Deny by default. Check role AND ownership on every endpoint (a farmer edits only their own products). Admin accounts are never self-registered. Store adapters may call only allow-listed hosts. | Yes | Partly: admin blocked, order prices server-side. Ownership checks come with the API |
| **A02 Security Misconfiguration** | HTTPS only, security headers, debug off, no default accounts, `FARM_ENV=production` skips sample data, uploads and DB outside the web root | Yes | To do at deployment |
| **A03 Software Supply Chain Failures** | Pin versions, run `pip-audit` in CI, enable Dependabot, install only from PyPI, review new packages | Yes | To do (CI) |
| **A04 Cryptographic Failures** | Passwords hashed with scrypt + salt, TLS in transit, secrets in environment variables, never in git | Yes | Hashing done. TLS at deployment |
| **A05 Injection** | Parameterized SQL only, validate all input, sanitize FTS queries | Yes | Done and tested |
| **A06 Insecure Design** | Server computes prices and stock, upload pipeline fails closed, rate limits on login and `/compare` | Yes | Prices, stock, uploads and a search rate limit (10 per minute per user) done |
| **A07 Authentication Failures** | 8+ char passwords, lockout after 5 failures for 15 min, same message for unknown email and wrong password, equal timing | Yes | Done and tested. MFA and breached-password check are future work |
| **A08 Software or Data Integrity Failures** | Verify Paystack/Flutterwave webhook signatures, re-encode uploaded images, protect the main branch | Yes | Uploads done. Webhook with payment phase |
| **A09 Security Logging and Alerting Failures** | Log login failures, lockouts, rejected uploads, scanner outages. Never log passwords, tokens or full emails. Alert on bursts | Yes | Logging done. Alerting at deployment |
| **A10 Mishandling of Exceptional Conditions** | Fail closed, show generic messages, log details server-side, one failing store never breaks search | Yes | Done for uploads, search, stores. API error handler later |

## ClamAV upload scanning

Every uploaded photo goes through `app/uploads.py`, in this order. Any failure rejects the file.

1. 5 MB size limit
2. Real file type from its bytes (JPG, PNG, WebP). The extension is ignored
3. Full decode, with a pixel limit against decompression bombs
4. **ClamAV scan** over the clamd INSTREAM protocol
5. Re-encode with Pillow, which removes EXIF/GPS data and any hidden payload
6. Save under a random name

**If ClamAV is down, uploads are refused (fail closed).** They are never accepted unscanned.

Run ClamAV next to the app:
```bash
docker run -d --name clamav -p 3310:3310 clamav/clamav:stable   # wait a few minutes for signatures
export FARM_CLAMAV_HOST=127.0.0.1 FARM_CLAMAV_PORT=3310
```
Test it with the harmless EICAR file from eicar.org: upload it and confirm it is blocked.

Limits: ClamAV is signature-based and cannot catch everything. That is why steps 2, 3 and 5 exist as extra layers.

## Before every release
- [ ] `pytest -q` passes
- [ ] `pip-audit` reports no known vulnerabilities
- [ ] No secrets in git (`git log -p | grep -i "key\|secret\|password"`)
- [ ] `FARM_ENV=production`, HTTPS on, ClamAV running and EICAR blocked
- [ ] Sample accounts do not exist in the production database
