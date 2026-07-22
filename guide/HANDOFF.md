# Handoff

This project is ready for handoff as of July 22, 2026.

It is a Paynkolay Virtual POS test automation platform with a browser UI, API routes,
parallel execution, headless 3D Secure automation, PaymentList verification, cancel smoke
support, and sanitized reporting.

## What Is Ready

- Single payment testing through the Payment screen.
- MoTo and 3D Secure payment initialization.
- Headless 3D Secure completion for supported simulator cards.
- Parallel 3D Secure runs through the Parallel screen.
- Parallel UI is auto-3DS only and shows a simplified results table:
  `Card`, `Status`, `Class`, `PaymentList`, `3DS Auto`, `Duration`.
- Parallel UI shows success rate from completed classifications, e.g. `19/20 (95.0%)`.
- Runtime card and environment visibility through Settings.
- Allure/report/evidence review through Reports.
- Sanitized parallel evidence under `reports/parallel-runs/`.
- Local/mock and guarded UAT validation paths.

## Do Not Change Without A Reason

- Payment screen: current behavior is validated and should remain stable.
- Settings screen: current behavior is validated and should remain stable.
- Card secret handling: never commit PAN, CVV, OTP, merchant secret, SX, hashes, signatures,
  or raw ACS HTML.
- Random automatic success selection: keep it restricted to explicit success candidates.

## Current UAT Environment Contract

Provider base URL:

```text
https://paynkolaytest.nkolayislem.com.tr/Vpos
```

Default callback/final return endpoint:

```text
https://paynkolay.com.tr/test/callback
```

For UAT, the callback is treated as the final endpoint. Do not append local callback/result
paths to it.

`make uat-inputs` builds runtime config and scenario catalog from ignored credential
artifacts.

## Current Card Status

Automatic success candidates:

- `nkolay_dynamic_otp_visa_6111`
- `akbank_visa_7068`

Diagnostic cards:

- `garanti_bankasi_mastercard_6017`
- `akbank_visa_5232`

Manual-only and quarantined cards are still useful for diagnostics, but they should not be
used in random success runs.

## Important Recent Evidence

- N Kolay Visa baseline completed 50/50 in parallel UAT.
- Headless web 3DS completed successfully without opening a visible tab:
  - status: `completed`
  - PaymentList: `captured`
  - automation: `completed submitted source=visible_page reason=otp_submitted`
- Earlier Garanti parallel behavior showed required-field validation and provider
  finalization instability. Treat Garanti as diagnostic unless deliberately retesting it.

## Headless 3DS Notes

The key fix is in `src/paynkolay_pos/three_ds/acs_browser.py`.

The QNB ACS simulator rejected pure headless Chromium because of the `HeadlessChrome`
user-agent. Headless contexts now use a normal Chrome-like user-agent while still running
in the background.

If this regresses, look for:

- `_404`
- `404-QPG97-STATUS`
- `acs_browser_client_rejected`
- `otp_selector_not_found`
- `failed not-submitted source=no-source`
- `provider payment status verification failed`
- `otp_submitted_callback_not_reached`
- `Page.set_content: Timeout 30000ms exceeded`

`acs_browser_client_rejected` means the browser identity was rejected. `no-source` means no
safe OTP source was found.

Recent resilience tuning:

- Submitted parallel 3DS flows now use PaymentList retry delays of `2s, 5s, 10s, 20s`.
- ACS initial content rendering now allows 60 seconds before classifying a Playwright
  content-load timeout.
- `payment_list_missing` after `otp_submitted` usually means provider/PaymentList timing,
  not a card decline.
- `framework_error` with `Page.set_content` means the ACS browser automation timed out
  before OTP processing.

## How To Start The UI

Local/mock:

```bash
make web
```

UAT, normal headless 3DS:

```bash
make uat-web WEB_PORT=8001 WEB_RELOAD=--reload
```

UAT with visible browser tabs for debugging:

```bash
make uat-web WEB_PORT=8001 WEB_RELOAD=--reload WEB_3DS_HEADED=1 WEB_3DS_CLOSE_DELAY=5
```

## Useful Smoke Commands

```bash
make uat-3ds-smoke
make uat-parallel-3ds-smoke
make uat-cancel-smoke
make credential-scenario-report
make report
```

## Validation Before Shipping Changes

Run:

```bash
poetry run ruff check .
poetry run mypy src tests tools
poetry run pytest -q
git diff --check
```

Latest known status:

```text
pytest api web     60 passed
pytest acs browser 12 passed
ruff check        passed
mypy             passed
pytest           342 passed, 5 skipped
git diff check   passed
```

## Current Unfinished Business

There is no required implementation work left for the current project scope.

Possible future work:

- support 100-150 item parallel execution as a deliberate scaling task,
- add official negative UAT tests when Paynkolay provides stable negative card data,
- replace installment stubs if Paynkolay provides the real endpoint contract,
- expand cancel reporting if provider semantics are clarified.

## Safe Handoff Rule

When investigating a failed payment, first decide whether the failure belongs to:

- the framework,
- Paynkolay/provider response,
- ACS/bank simulator behavior,
- PaymentList timing,
- network/environment.

The project already records enough sanitized metadata to make that distinction in most
cases.
