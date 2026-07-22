# Project Memory

This file is the short memory for future sessions. Read this first, then `guide/HANDOFF.md`
and `README.md` if more context is needed.

Never move private data into tracked files. `credentials/` is ignored and must remain the
place for local-only card, merchant, SX, OTP, hash, and provider artifacts.

## Final State - July 22, 2026

The project is considered feature-complete and presentation-ready.

It provides a tester-facing FastAPI web UI for:

- single Paynkolay payment tests,
- MoTo and 3D Secure flows,
- card selection and form-fill,
- parallel test runs,
- PaymentList verification,
- report and evidence review,
- runtime settings overview.

The current UI polish scope is also complete:

- Payment screen was left untouched because it already works well.
- Settings screen was left untouched because it already works well.
- Parallel screen now uses the available page width instead of staying narrow.
- Parallel result table is presentation-oriented and shows only:
  `Card`, `Status`, `Class`, `PaymentList`, `3DS Auto`, and `Duration`.
- Parallel result rows use light green for completed classifications and light red for
  attention/failure classifications.
- Parallel summary shows a success rate calculated from `classification == "completed"`
  results, e.g. `19/20 (95.0%)`.
- Parallel runs always use automatic 3DS completion from the UI. Manual 3DS mode remains
  available on the single Payment screen only.
- Reports screen now uses wider, more readable panels and tables.
- Long strings in Parallel and Reports are less cramped for business analyst review.

## Current Card Automation Policy

Random/default automatic 3D Secure success runs must use only explicit success candidates.

Current automatic success pool:

- `nkolay_dynamic_otp_visa_6111`
- `akbank_visa_7068`

Current diagnostic pool:

- `garanti_bankasi_mastercard_6017`
- `akbank_visa_5232`

Current manual-only / quarantined behavior should stay excluded from random success runs
unless fresh UAT evidence proves otherwise.

Important live UAT observations:

- `nkolay_dynamic_otp_visa_6111` is the baseline card. It completed a 50/50 parallel UAT run.
- `akbank_visa_7068` performed strongly across repeated 10-item parallel runs, but had
  intermittent failures in larger repeated observations.
- Garanti can show required-field validation issues or provider finalization failures under
  parallel automation. Keep it diagnostic unless deliberately retesting it.
- The framework should distinguish provider/ACS behavior from framework errors.

## Headless 3DS Resolution

The latest important fix was headless 3D Secure automation.

Root cause:

- QNB ACS/simulator rejected headless Chromium when the browser identified itself with a
  `HeadlessChrome` user-agent.
- The page returned `_404 / 404-QPG97-STATUS`.
- Earlier diagnostics could misleadingly appear as `otp_selector_not_found`.

Implemented behavior:

- Headless browser contexts now use a normal Chrome-like user-agent.
- Headed mode remains unchanged.
- QNB client rejection is classified as `acs_browser_client_rejected`.
- Dynamic OTP cards can use the visible page OTP even when no static `expected_otp` is
  configured.
- ACS frame evidence is sanitized before being stored.

Confirmed after the fix:

- Web UI headless 3DS completed without opening a visible tab.
- Payment status was `completed`.
- PaymentList status was `captured`.
- 3DS automation showed `completed submitted source=visible_page reason=otp_submitted`.

Current resilience tuning:

- Parallel 3DS PaymentList verification uses the longer retry window
  `2s, 5s, 10s, 20s` after OTP submit. This is meant to reduce transient
  `payment_list_missing` / `provider payment status verification failed` results.
- ACS initial HTML rendering timeout was raised to 60 seconds to reduce transient
  `Page.set_content: Timeout 30000ms exceeded` failures under parallel UAT load.
- These changes do not convert provider declines to success; they only give submitted
  3DS flows more time to finalize and render.

## Parallel Run Limits

The old 10-item cap was raised to 50.

Current intended UI/API behavior:

- Manual selections cannot exceed 50 total test items.
- Random count cannot exceed 50.
- Concurrency input cannot exceed 50.
- Evidence is written under `reports/parallel-runs/`.

The user has a new external requirement to eventually run 100-150 parallel items. That is
not implemented yet. If it is picked up later, treat it as a capacity/scaling change rather
than a simple UI limit change.

## Validation Snapshot

Latest known local validation after headless 3DS work:

```text
poetry run pytest tests/api/test_web_app.py -q          60 passed
poetry run pytest tests/three_ds/test_acs_browser.py -q 12 passed
poetry run pytest -q    342 passed, 5 skipped
poetry run ruff check . passed
git diff --check        passed
```

Earlier full checks also had mypy passing. Re-run the full gate before any release commit.

## Important Commands

Start local web UI:

```bash
make web
```

Start UAT web UI:

```bash
make uat-web WEB_PORT=8001 WEB_RELOAD=--reload
```

Use visible browser tabs only for debugging:

```bash
make uat-web WEB_PORT=8001 WEB_RELOAD=--reload WEB_3DS_HEADED=1 WEB_3DS_CLOSE_DELAY=5
```

Run guarded UAT smoke checks:

```bash
make uat-3ds-smoke
make uat-parallel-3ds-smoke
make uat-cancel-smoke
```

Run local validation:

```bash
poetry run ruff check .
poetry run mypy src tests tools
poetry run pytest -q
git diff --check
```

## Files To Know

- `src/paynkolay_pos/api/routes/parallel_runs.py`: parallel run API and item execution.
- `src/paynkolay_pos/api/payment_list_retry.py`: PaymentList retry/backoff.
- `src/paynkolay_pos/testing/card_behaviors.py`: safe card automation metadata.
- `src/paynkolay_pos/three_ds/acs_browser.py`: Playwright ACS automation.
- `src/paynkolay_pos/three_ds/acs_profile.py`: ACS screen classification.
- `src/paynkolay_pos/three_ds/otp_resolver.py`: OTP source decisioning.
- `src/paynkolay_pos/web/templates/parallel.html`: Parallel page layout.
- `src/paynkolay_pos/web/templates/report.html`: Reports page layout.
- `src/paynkolay_pos/web/static/css/app.css`: shared UI styling.
- `tools/run_uat_parallel_3ds_smoke.py`: guarded parallel UAT smoke CLI.
- `tools/run_uat_3ds_smoke.py`: guarded single 3DS UAT smoke CLI.

## Future Work

Only provider-dependent or optional work remains:

- get official negative UAT card/CVV/OTP data,
- connect a real installment service if Paynkolay provides the contract,
- clarify cancel reporting semantics if Paynkolay exposes a separate listing rule,
- design a controlled 100-150 item parallel execution mode with capacity limits, telemetry,
  and provider-safe throttling.
