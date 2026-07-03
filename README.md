# Paynkolay Sanal POS Automation

Python test automation framework for Paynkolay Sanal POS payment flows.

The framework currently provides a provider-ready foundation with mocked/local validation
for Paynkolay form payments, transaction verification, cancel/refund operations,
callback verification, 3D Secure challenge automation, data-driven scenarios, reporting
evidence sanitization, and CI.

## Current Capabilities

- Strict runtime configuration for environments, merchants, and test cards.
- Typed payment request, response, status, and callback models.
- HMAC signature generation plus Paynkolay SHA-512/Base64 hash helpers.
- Async HTTP client for payment initialization, transaction status, and cancel/refund
  form endpoints.
- Business-level payment flow orchestration.
- Callback signature verification and in-memory callback matching.
- 3D Secure challenge helper with fake-page and local Playwright browser tests.
- Test data factories for reusable payment, status, and callback payloads.
- Scenario catalogue models for data-driven payment cases.
- Sanitized reporting evidence helpers for Allure attachments.
- GitHub Actions validation workflow, including a browser-backed 3DS job.

Implemented Paynkolay form endpoints:

- `POST /v1/Payment`
- `POST /Payment/PaymentList`
- `POST /v1/CancelRefundPayment`

## Tech Stack

- Python 3.11+
- Poetry
- Pytest and pytest-asyncio
- HTTPX async client
- Pydantic v2
- Playwright Python
- Allure Pytest
- Ruff
- Mypy strict mode

## Setup

Install dependencies:

```bash
poetry install --no-interaction
```

Run the standard validation set:

```bash
poetry check
poetry run ruff check .
poetry run mypy src tests
poetry run pytest
```

Run only 3D Secure tests:

```bash
poetry run pytest -m three_ds
```

The browser-backed 3DS test requires Chromium binaries:

```bash
poetry run playwright install chromium
```

Without browser binaries, that specific browser test skips locally. CI installs Chromium in
the dedicated 3DS browser job.

Load the example payment scenario catalogue:

```python
from paynkolay_pos.scenarios import load_payment_scenario_catalog

catalog = load_payment_scenario_catalog("examples/scenarios/payment_scenarios.json")
print(catalog.ids())
```

## Project Layout

```text
src/paynkolay_pos/
  callbacks/   Callback signature verification and callback store
  clients/     Async provider HTTP client
  config/      Runtime environment, merchant, and card settings
  flows/       Business-level payment flow orchestration
  models/      Payment and callback Pydantic models
  reporting/   Sanitized evidence helpers for reports
  scenarios/   Data-driven payment scenario metadata
  security/    Canonicalization, HMAC, and Paynkolay hash helpers
  testing/     Reusable test data factories
  three_ds/    3D Secure browser challenge helper
```

## What Is Mocked Today

The framework is intentionally ready before real Paynkolay sandbox details are available.
Current tests use:

- `httpx.MockTransport` for provider API responses.
- Local/fake callback payloads with real HMAC verification.
- Fake and local Playwright-style 3DS challenge pages.
- Example scenario data in `examples/scenarios/payment_scenarios.json`.
- Placeholder endpoint paths:
  - `POST /payments/initialize`
  - `GET /payments/{order_id}/status`
- Paynkolay API v1 form endpoint calls are mocked locally until private sandbox
  credentials are available.

## External Details Needed For Real Sandbox E2E

To switch from framework validation to real Paynkolay sandbox validation, collect:

- Sandbox base URL.
- Merchant ID, terminal ID, API key, and secret/hash key.
- Exact initialize/status endpoint paths.
- Exact request and response field names.
- Exact signature algorithm, field order, separator, and encoding rules.
- Callback payload format and callback signature rules.
- Test card catalogue, expected statuses, and 3DS OTP values.
- 3DS sandbox page selectors or documented challenge flow.
- Installment, MoTo, currency, capture, and detailed sandbox business rules.

## Safety Rules

Do not expose full PAN, CVV, OTP, API keys, secret keys, signatures, or tokens in logs or
reports. Use `paynkolay_pos.reporting.sanitize_evidence()` or
`attach_json_evidence()` before attaching payloads to Allure.

The local `guide/` folder is intentionally ignored by Git and is not part of the public
project documentation.
