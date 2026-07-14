# Paynkolay Sanal POS Automation

Paynkolay Sanal POS Automation is a test automation and validation framework for
Paynkolay virtual POS payment flows. The project supports local/mock validation,
data-driven scenario execution, browser-based 3D Secure handling, UAT smoke testing,
transaction verification, cancel/refund checks, and sanitized reporting.

The system is designed for integration testing and QA workflows. It is not a production
payment gateway.

## Project Purpose

The framework was built to automate and observe the lifecycle of Sanal POS transactions
across different cards, payment flows, environments, and expected outcomes. It provides a
tester-facing web UI and a repeatable test suite so payment scenarios can be executed,
verified, and reported without changing application code.

Main objectives:

- Validate Paynkolay payment initialization through configured environments.
- Support MoTo and 3D Secure payment flows.
- Verify final transaction state through PaymentList.
- Exercise cancel/refund endpoint behavior.
- Manage test cards and scenarios from external configuration.
- Produce sanitized test evidence and Allure reports.
- Keep private merchant credentials, PAN, CVV, OTP, and secrets outside the repository.

## High-Level Architecture

```text
Browser UI / Test Runner
        |
        v
FastAPI Web/API Layer
        |
        v
Payment Initializer / Flow Orchestration
        |
        v
Paynkolay Client
        |
        v
Paynkolay UAT / Mock Provider Responses
```

Core modules:

- `api/` exposes the tester UI, payment routes, result pages, card management, report
  endpoints, and 3D Secure rendering.
- `clients/` contains the Paynkolay HTTP boundary for payment, PaymentList, and
  cancel/refund form endpoints.
- `models/` defines typed payment, provider result, callback, and status objects.
- `security/` implements Paynkolay SHA-512/Base64 hash helpers and generic signature
  verification utilities.
- `config/` loads runtime environment, merchant, callback, and card settings.
- `scenarios/` defines data-driven payment scenario metadata.
- `three_ds/` renders provider 3D Secure forms and supports browser automation helpers.
- `reporting/` sanitizes evidence before terminal output or Allure reporting.

## Payment Lifecycle

A payment starts from the browser UI or an automated test. The request is validated,
mapped to a typed payment model, signed according to the Paynkolay form contract, and
sent to the selected provider environment.

For MoTo payments, Paynkolay returns a final provider result. The framework parses the
response, evaluates the payment status, stores sanitized session state, and verifies the
transaction through PaymentList.

For 3D Secure payments, Paynkolay returns `BANK_REQUEST_MESSAGE`. The framework stores
that provider form transiently and exposes it through the browser so the bank/ACS
challenge can be completed. After the provider return, the result payload is verified with
`hashDataV2`, then the session is marked as completed or failed.

## Supported Paynkolay Services

The implementation is aligned with these Paynkolay form endpoints:

- `POST /v1/Payment`
- `POST /Payment/PaymentList`
- `POST /v1/CancelRefundPayment`

Request hash generation and response hash verification are implemented with the documented
field order and SHA-512/Base64 format.

## Tester UI

The web UI provides a practical payment test dashboard:

- payment form for MoTo and 3D Secure flows,
- runtime card list with alias, brand, card, expiry, flow, and action columns,
- test card addition from the UI,
- secure/MoTo filtering and search,
- automatic form-fill from selected test cards,
- local installment option stub until the real installment service is available,
- result panel with provider reference, PaymentList status, and authorization code,
- 3D Secure render link when Paynkolay returns a browser challenge,
- report page for generated Allure output.

The card list intentionally exposes test PAN/CVV to the local tester UI. It should only be
used with private UAT/test card data.

## Runtime Configuration

Runtime configuration is externalized through JSON and environment variables. The active
config supplies:

- provider base URL,
- callback/final return URL,
- merchant identifiers,
- Paynkolay `sx` values,
- merchant secret key,
- test card catalogue,
- selected environment: `dev`, `uat`, or `test`.

Private files are expected to live outside Git or under ignored local paths such as
`credentials/` and `/tmp`.

Typical runtime variables:

```bash
PAYNKOLAY_CONFIG_FILE=/tmp/paynkolay-uat-settings.json
PAYNKOLAY_SCENARIO_CATALOG=/tmp/paynkolay-credential-scenarios.json
PAYNKOLAY_ENV=uat
```

## UAT Status

The framework has been exercised against the Paynkolay UAT/test environment.

Confirmed flows:

- MoTo payment initialization and approval.
- PaymentList verification after successful payment.
- 3D Secure initialization through `BANK_REQUEST_MESSAGE`.
- Manual browser 3D Secure completion through the tester UI.
- Headless Playwright 3D Secure OTP automation for web and parallel tester flows.
- Same-day cancel request through `/v1/CancelRefundPayment`.

Known UAT notes:

- 3D Secure ACS behavior may differ by issuer simulator and card profile.
- Reliable negative UAT testing requires official invalid card/CVV/OTP data from the
  provider.
- PaymentList may continue to show the original sales row after cancel; the cancel service
  response is currently treated as the primary cancel evidence.

## Reporting

The project supports Allure reporting for local and credential-driven validation. Evidence
is sanitized before being attached or printed. Sensitive fields such as PAN, CVV, OTP,
merchant secrets, hashes, signatures, and raw 3D Secure HTML are redacted.

Generate a report:

```bash
make report
```

Open the generated report:

```bash
allure open allure-report
```

## Common Commands

Install dependencies:

```bash
make install
```

Run the local quality gate:

```bash
make check
```

Start the local web UI:

```bash
make web
```

Start the UAT tester UI:

```bash
make uat-web
```

The tester UI runs 3D Secure automation headless by default so parallel runs do not open
one visible browser window per card. For visual debugging, pass
`WEB_3DS_HEADED=1 WEB_3DS_CLOSE_DELAY=5`.

Run guarded UAT smoke checks:

```bash
make uat-3ds-smoke
make uat-cancel-smoke
```

Generate credential scenario report:

```bash
make credential-scenario-report
```

## Validation

The standard local validation suite covers API routes, models, provider client behavior,
hash generation, callback handling, scenario catalogues, mocked end-to-end flows, reporting
sanitization, and 3D Secure helpers.

Current validation status:

```text
ruff check        passed
mypy             passed
pytest           251 passed, 5 skipped
```

Skipped tests are live/sandbox-gated tests that require private runtime configuration and
explicit live execution flags.

## Security And Data Handling

- Private credentials and card data are not committed.
- `credentials/` is ignored by Git.
- PAN, CVV, OTP, secrets, hashes, signatures, and raw 3DS HTML are sanitized in evidence.
- Runtime card data is loaded from external configuration.
- UAT/live tests are guarded to avoid accidental provider calls.

## Technology Stack

- Python 3.11+
- FastAPI
- HTTPX
- Pydantic v2
- Pytest
- Playwright
- Allure Pytest
- Ruff
- Mypy
- Poetry

## Current Scope

The project is presentation-ready for:

- local/mock validation,
- UAT payment demo through the web UI,
- MoTo payment and PaymentList verification,
- 3D Secure initialization and manual browser completion,
- same-day cancel smoke checks,
- card-list based tester workflows,
- local installment option stubbing,
- sanitized Allure reporting.

Remaining work is primarily provider-dependent:

- connect the real installment service,
- obtain reliable negative UAT test data,
- finalize fully automated parallel 3D Secure OTP handling,
- clarify final cancel reporting semantics with Paynkolay if needed.
