# Cloudflare Environment - sc_log_reader donate

> Operational state of the Cloudflare infrastructure backing the log-donation feature.
> For other agents (skill side or worker side) picking up this work in future sessions.
>
> Set up: 2026-05-14
> Owner: Mallachi (lars.erik.vaagen@gmail.com)

## Status: LIVE

Worker is deployed, all five secrets are set, end-to-end flow verified.
D1 and R2 are empty after smoke-test cleanup. Ready for the skill side
to start donating real logs.

---

## Cloudflare account

| Field | Value |
|---|---|
| Email | lars.erik.vaagen@gmail.com |
| Account ID | `cd7b89f1bdd1ddaace0b35e3127140a9` |
| Plan | Free (Workers / R2 / D1 free tiers comfortably cover initial usage) |

**Critical caveat.** The user has a second Cloudflare account ("SC Bridge",
`92557ddeffaf43d64db74acf783ec49d`) used for an unrelated project. The
`CLOUDFLARE_ACCOUNT_ID` env var in their shell startup points at SC Bridge.
`sc-log-donate` is NOT on SC Bridge. Every wrangler call must override
`CLOUDFLARE_ACCOUNT_ID` to the personal account.

The `CLOUDFLARE_API_TOKEN` in `~/.secrets` IS already scoped to the personal
account (verified active, expires 2026-06-30).

### Required PowerShell preamble for any wrangler call

```powershell
$secrets = Get-Content "$HOME\.secrets" -Raw
$env:CLOUDFLARE_API_TOKEN = [regex]::Match($secrets, 'CLOUDFLARE_API_TOKEN\s*=\s*"?([^"\r\n]+)"?').Groups[1].Value.Trim()
$env:CLOUDFLARE_ACCOUNT_ID = "cd7b89f1bdd1ddaace0b35e3127140a9"   # MUST override
Set-Location D:\PycharmProjects\sc-log-donate
npx wrangler <command>
```

---

## Resources

### Worker

| Field | Value |
|---|---|
| Script name | `sc-log-donate` |
| URL | `https://sc-log-donate.lars-erik-vaagen.workers.dev` |
| Source repo | `D:\PycharmProjects\sc-log-donate\` |
| `workers.dev` subdomain | `lars-erik-vaagen.workers.dev` (registered 2026-05-14) |
| Initial version ID | `76235817-2f91-4abc-a9b7-5a14181dac23` |

### D1

| Field | Value |
|---|---|
| Database name | `sc-log-donate-meta` |
| UUID | `17ae60be-1490-40d1-886b-757738e1d008` |
| Region | EEUR |
| Schema | `migrations/0001_initial.sql` applied to remote |
| Tables | `uploads`, `file_hashes` (+ supporting indexes) |
| Row count | 0 (cleaned after smoke verification) |

### R2

| Field | Value |
|---|---|
| Bucket | `sc-log-donations` |
| Storage class | Standard |
| Object count | 0 (cleaned after smoke verification) |
| API access | R2 API token created in CF dashboard 2026-05-14, scoped Object Read and Write on this bucket only |

---

## Worker secrets

All five set via the Cloudflare API (`PUT /accounts/{id}/workers/scripts/sc-log-donate/secrets`).

NOTE for future agents: do NOT set secrets via `wrangler secret put` piped from
PowerShell stdin. PowerShell appends a trailing newline that ends up inside
the stored secret and breaks header-equality comparison. Use the CF API
directly (Invoke-RestMethod with the secret as JSON `text`).

| Secret name | Provenance |
|---|---|
| `DONOR_TOKEN` | 32-char hex, cryptographically random, generated 2026-05-14 by `[System.Security.Cryptography.RandomNumberGenerator]`. Value held by the user. Must be supplied at skill-build time so `update_release.py` can substitute it into `release_version/default_config.yaml`. Not stored in any committed file. |
| `R2_ACCESS_KEY_ID` | Public half of the R2 API token. |
| `R2_SECRET_ACCESS_KEY` | Secret half of the R2 API token. |
| `R2_ACCOUNT_ID` | `cd7b89f1bdd1ddaace0b35e3127140a9` (personal CF account). |
| `R2_BUCKET_NAME` | `sc-log-donations`. |

---

## Smoke verification (2026-05-14)

All steps green against the deployed Worker:

1. `GET /healthz` -> `200 ok`
2. `POST /upload/begin` without `X-Donor-Token` -> `401`
3. `POST /upload/begin` with valid token + sample body -> `200`, returns `upload_id` + presigned R2 PUT URL (10-min expiry, AWS4-HMAC-SHA256, key `YYYY-MM-DD/{upload_id}/{install}/{renamed}`)
4. `PUT` of 22-byte payload to the presigned URL -> `200`, file landed in R2
5. `POST /upload/complete` -> `200`, D1 `uploads.complete = 1`, `file_hashes` row inserted, `manifest.json` written to R2 at `YYYY-MM-DD/{upload_id}/manifest.json`

D1 + R2 wiped post-smoke; baseline is clean.

---

## What is NOT done

| Item | Status | Why |
|---|---|---|
| Cloudflare WAF rate-limit rule (`/upload/begin` 10 req/min/IP) | Deferred | Free plan doesn't expose WAF rate-limit rules. Initial rollout relies on `DONOR_TOKEN` gating + social-trust scale. If abuse appears later, add a Workers-native rate-limit binding (`[[unsafe.bindings]] type = "ratelimit"`) - stays on free plan, ~30 lines of code. |
| Skill-side build wiring (`update_release.py`) | Pending | The skill's `default_config.yaml` per spec has `worker_url: ""` and `worker_token: "__INJECT_AT_BUILD__"`. `update_release.py` must read `DONOR_TOKEN` from env at build time and substitute both placeholders into `release_version/default_config.yaml`. Belongs to the skill plan (see RESUME-2026-05-14.md, Skill Task ~8). |
| `skill_installer_config.json` bump | Pending | New `donor.*` config keys not yet baked into installer. Part of skill-side work. |
| GitHub Actions deploy workflow (worker-plan Task 15) | Optional | Manual `npm run deploy` works. Add CI later if cadence justifies it. |
| Reconciler script (worker-plan Task 11) | Pending | Not blocking initial rollout; sweep for stale incomplete uploads is only useful once there's real traffic. |

---

## How future agents should pick this up

### Worker side (`D:\PycharmProjects\sc-log-donate\`)

- Resume from worker-plan Task 8 onward (the `/upload/begin` happy path and dedup branch are in; T9 `/upload/complete` exists in code per the file structure but verify against latest commits).
- Use the env-var preamble above. `wrangler whoami` correctly reports the personal account because that's derived from the token, but the underlying API calls still use `CLOUDFLARE_ACCOUNT_ID`. Override or you'll hit 401s on D1/R2 operations.
- The remote D1 + R2 are live; you can integration-smoke directly against `https://sc-log-donate.lars-erik-vaagen.workers.dev`.
- `wrangler.toml` now carries the real `database_id` (`17ae60be-...`). Don't revert it to the placeholder.

### Skill side (`skills/sc_log_reader/log_donor/`)

- Resume per `skills/sc_log_reader/plans/RESUME-2026-05-14.md` (Skill Task 4 onward).
- The donor module's uploader should target:
  ```yaml
  donor:
    worker_url: "https://sc-log-donate.lars-erik-vaagen.workers.dev"
    worker_token: "__INJECT_AT_BUILD__"
  ```
- For local end-to-end testing, ask the user for the live `DONOR_TOKEN` value (stored only as Worker secret + in user's local notes) or generate a temporary one and `secret put` it for the test, then restore.
- `update_release.py` will need a new env-var read (`DONOR_TOKEN`) and a substitution into `release_version/default_config.yaml`.

### Operational

- Rotating `DONOR_TOKEN`: regenerate, push via the CF-API path documented above (avoid the wrangler stdin gotcha), update `update_release.py`'s build env, re-release skill. Old skill versions will 401 until they update.
- Browsing donated logs: CF dashboard -> R2 -> sc-log-donations, or `rclone` configured with the R2 S3 endpoint + the existing R2 API token.
- Querying D1: `npx wrangler d1 execute sc-log-donate-meta --remote --command "..."` with the env-var preamble.

---

## Common gotchas to know before touching this

1. **`CLOUDFLARE_ACCOUNT_ID` default points to the wrong account.** Always override to `cd7b89f1bdd1ddaace0b35e3127140a9`. `wrangler whoami` will mislead you - it reads the account from the token, not the env var, so it looks correct while everything else fails with `Authentication error [code: 10000]`.

2. **PowerShell pipe to `wrangler secret put` appends a newline.** The stored secret will not equal the value you piped. Use the CF API to set secrets cleanly.

3. **Free plan does not include WAF rate-limit rules.** If a future agent tries to follow worker-plan Task 14 verbatim, they'll need to either upgrade the account or implement Workers-native rate limiting.

4. **R2 API token can only be created in the dashboard.** Wrangler can create R2 buckets but cannot mint R2 access keys. User must do that step manually each time the credentials need rotating.

5. **`workers.dev` subdomain is a one-time per-account onboarding.** Already done as `lars-erik-vaagen.workers.dev` - no action needed unless the user changes accounts.
