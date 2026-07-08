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
make install
```

The direct Poetry equivalent is:

```bash
poetry install --no-interaction
```

## One-Click Commands

The project exposes common setup, validation, execution, reporting, and cleanup commands
through `make`.

Show the available commands:

```bash
make help
```

Run the standard validation set:

```bash
make check
```

Run the browser-based FastAPI web UI:

```bash
make web
```

By default the UI is served at `http://127.0.0.1:8000`. Override the bind address with
`WEB_HOST` and `WEB_PORT`; pass `WEB_RELOAD=--reload` during local development when file
watching is available.

The web UI can load without private runtime configuration, but payment submission requires
`PAYNKOLAY_CONFIG_FILE` so the backend can build Paynkolay form requests with merchant,
callback, success, and fail URL settings.

When Paynkolay returns a 3D Secure form, the web API stores the provider form transiently
and serves it at `/payments/{order_id}/three-ds`. The payload may be raw HTML or base64
HTML; OTP entry remains on the bank/ACS form, not on the merchant UI.

Paynkolay success/fail returns are handled by `/payments/result/success` and
`/payments/result/fail`. These endpoints accept GET query parameters or POST form fields,
verify `hashDataV2` with the active merchant secret key, update the payment session, and
render a sanitized result page.

External payment event logging is disabled by default. Set `PAYNKOLAY_EXTERNAL_LOG_URL`
to send sanitized event payloads to an external HTTP endpoint. Optional
`PAYNKOLAY_EXTERNAL_LOG_TIMEOUT_SECONDS` controls the request timeout. External logs never
include full PAN, CVV, OTP, merchant secrets, API keys, hashes, or raw 3DS HTML.

Run the full test suite only:

```bash
make test
```

Run tests in parallel with `pytest-xdist`:

```bash
make parallel
```

Run only 3D Secure tests:

```bash
make three-ds
```

Run focused test groups:

```bash
make smoke
make api
make callback
make scenarios
make scenarios-file SCENARIO_FILE=/tmp/paynkolay-synthetic-scenarios.json
make negative
```

Validate private sandbox readiness without running payments:

```bash
export PAYNKOLAY_CONFIG_FILE=/path/outside/git/paynkolay-settings.json
export PAYNKOLAY_SCENARIO_CATALOG=/path/outside/git/sandbox-scenarios.json
make sandbox-ready
```

Generate a synthetic 100-card JSON array for a private config:

```bash
make synthetic-cards
```

Generate a synthetic 1000-scenario catalogue:

```bash
make synthetic-scenarios
```

Generate and run a 100-card / 1000-scenario scale demo:

```bash
make scale-demo
make scale-demo-parallel
```

Generate Allure result files:

```bash
make allure-results
```

Generate an Allure HTML report:

```bash
make report
```

`make report` requires the Allure command-line tool. On macOS, install it with:

```bash
brew install allure
```

The generated HTML report is written to `allure-report/`. The raw pytest Allure files
are written to `allure-results/`.

The `/reports` page calls `/api/reports/latest` and reports whether
`allure-report/index.html` exists. Override the report directory for local experiments
with:

```bash
export PAYNKOLAY_ALLURE_REPORT_DIR=/path/to/allure-report
```

Remove generated local artifacts:

```bash
make clean
```

The browser-backed 3DS test requires Chromium binaries:

```bash
poetry run playwright install chromium
```

Without browser binaries, that specific browser test skips locally. CI installs Chromium in
the dedicated 3DS browser job.

## Tester UI Workflow

The web UI is the tester-facing entry point. It is useful for manual browser checks and
private sandbox validation once credentials are available.

Start the UI:

```bash
make web
```

Open:

```text
http://127.0.0.1:8000
```

If port `8000` is already in use, choose another port:

```bash
make web WEB_PORT=8001
```

Main tester pages:

- `/` - payment form.
- `/payments/{order_id}/three-ds` - transient provider 3DS form when Paynkolay returns
  `BANK_REQUEST_MESSAGE`.
- `/result?order_id={order_id}` - sanitized payment status lookup.
- `/reports` - local Allure report status.

Typical manual flow:

1. Start the web UI with `make web`.
2. Open `/` and submit card/payment fields.
3. If the response requires 3DS, open the 3DS link and complete the bank/ACS form.
4. After provider return, inspect `/result?order_id={order_id}`.
5. Use `/result` to manually look up any existing in-memory order ID.
6. Run `make report`, then open `/reports` to confirm local report availability.

Payment submission requires `PAYNKOLAY_CONFIG_FILE` because the backend must know the
selected merchant, Paynkolay base URL, success URL, fail URL, callback base URL, and
merchant secret. The UI can render without private config, but provider initialization
returns `503` until runtime config is available.

The result and report pages only show sanitized state. They must not display full PAN,
CVV, OTP, merchant secrets, API keys, `sx`, hashes, signatures, or raw 3DS HTML.

## Mock Vs Sandbox Execution

The default suite is safe for local development and CI. It uses mocked provider responses,
fake callback payloads, and local 3DS pages:

```bash
make test
make scale-demo
make report
```

Sandbox commands are reserved for private Paynkolay inputs. They require
`PAYNKOLAY_CONFIG_FILE`; most real provider calls also require `PAYNKOLAY_SCENARIO_CATALOG`
and an externally reachable callback URL:

```bash
make sandbox-ready
make sandbox
make sandbox-report
```

`make sandbox-ready` performs only offline checks. It validates that the selected private
config and scenario catalogue are internally consistent before any payment is attempted.
The live provider gate remains closed unless explicitly enabled:

```bash
export PAYNKOLAY_ENABLE_LIVE_E2E=1
make sandbox
```

Run the local callback receiver when the sandbox callback URL is tunneled or otherwise
reachable from Paynkolay:

```bash
export PAYNKOLAY_CALLBACK_SECRET=/replace/with/private/secret
python -m paynkolay_pos.callbacks.receiver --host 127.0.0.1 --port 8081 --path /callbacks/paynkolay
```

Do not commit private runtime configs, real PAN/CVV/OTP values, merchant credentials,
callback URLs, or generated reports containing real transaction evidence.

## Config And Data Strategy

Runtime settings and test data are intentionally kept outside test code. The framework
loads merchant, endpoint, callback, and card data from JSON, then uses scenario metadata
to decide which card and flow should run.

Create a private runtime config from the synthetic template:

```bash
cp examples/config/paynkolay-settings.example.json /path/outside/git/paynkolay-settings.json
export PAYNKOLAY_CONFIG_FILE=/path/outside/git/paynkolay-settings.json
```

Or generate a local-only skeleton with 100 cards per environment:

```bash
make private-config CONFIG_OUT=/tmp/paynkolay-private-settings.json
export PAYNKOLAY_CONFIG_FILE=/tmp/paynkolay-private-settings.json
```

Generate a matching local-only sandbox scenario catalogue:

```bash
make private-scenarios PRIVATE_SCENARIO_OUT=/tmp/paynkolay-private-scenarios.json
export PAYNKOLAY_SCENARIO_CATALOG=/tmp/paynkolay-private-scenarios.json
```

Create both files with one command:

```bash
make private-inputs \
  CONFIG_OUT=/tmp/paynkolay-private-settings.json \
  PRIVATE_SCENARIO_OUT=/tmp/paynkolay-private-scenarios.json \
  PRIVATE_ENV=dev
```

The generated private skeleton keeps the scenario-critical aliases such as
`visa_3ds_success`, `visa_installment_success`, `visa_moto_success`,
`visa_invalid_cvv`, `visa_debit_3ds_success`, and `visa_credit_3ds_success`, then
fills the remaining card slots with synthetic cards. Replace the placeholder merchant
credentials, callback URLs, PAN, CVV, expiry, and OTP values with Paynkolay sandbox data
before live sandbox execution.

The generated private scenario catalogue keeps the checked-in payment plan, adds the
`sandbox` tag required by readiness checks, and creates filler smoke scenarios so every
generated card alias is exercised.

Build a local/mock matrix from ignored credential CSV files:

```bash
make credential-matrix MATRIX_OUT=/tmp/paynkolay-credential-matrix.json
```

This reads local files under `credentials/`, normalizes test cards and CVV-driven error
codes, then writes a private JSON matrix for local/mock scenario planning. The generated
matrix may include PAN/CVV/OTP values and must stay outside Git.

Generate executable local/mock scenarios from the same credential files:

```bash
make credential-config CREDENTIAL_CONFIG_OUT=/tmp/paynkolay-credential-settings.json
make credential-scenarios CREDENTIAL_SCENARIO_OUT=/tmp/paynkolay-credential-scenarios.json
make credential-inputs \
  CREDENTIAL_CONFIG_OUT=/tmp/paynkolay-credential-settings.json \
  CREDENTIAL_SCENARIO_OUT=/tmp/paynkolay-credential-scenarios.json
make credential-scenario-test CREDENTIAL_SCENARIO_OUT=/tmp/paynkolay-credential-scenarios.json
make credential-scenario-report CREDENTIAL_SCENARIO_OUT=/tmp/paynkolay-credential-scenarios.json
```

Credential scenarios cover 3DS cards, MoTo candidates, credit/debit coverage, installment
candidates, and CVV-driven negative cases from `param_hata_kodlari.csv`.
`make credential-scenario-test` builds credential config plus scenarios, then executes the
generated catalogue against the mocked payment flow.
`make credential-scenario-report` runs the same mocked flow and generates an Allure HTML
report under `allure-report/`.
Export the generated config and scenario files before opening `/settings` when you want
the tester UI to display local/mock card and readiness metadata:

```bash
export PAYNKOLAY_CONFIG_FILE=/tmp/paynkolay-credential-settings.json
export PAYNKOLAY_SCENARIO_CATALOG=/tmp/paynkolay-credential-scenarios.json
```

Local/mock tester handoff:

```bash
make credential-inputs
export PAYNKOLAY_CONFIG_FILE=/tmp/paynkolay-credential-settings.json
export PAYNKOLAY_SCENARIO_CATALOG=/tmp/paynkolay-credential-scenarios.json
make credential-scenario-report
make web
```

Then open `/settings` to inspect the loaded credential cards and scenarios, and `/reports`
to confirm the generated Allure report.

Select an environment without editing the JSON file:

```bash
export PAYNKOLAY_ENV=uat
```

If `PAYNKOLAY_ENV` is not set, the file's `active_environment` value is used. Supported
environment names are `dev`, `uat`, and `test`.

The example config is schema-valid but synthetic. It demonstrates:

- separate `dev`, `uat`, and `test` environment blocks
- environment-specific merchant credentials
- environment-specific provider and callback URLs
- reusable test card aliases
- 3DS cards with `expected_otp`
- MoTo/non-3DS cards without OTP values

Each scenario in `examples/scenarios/payment_scenarios.json` references a card by
`card_alias`. That alias must exist in the selected environment's `cards` list. For
example:

```json
{
  "scenario_id": "visa_3ds_capture",
  "card_alias": "visa_3ds_success"
}
```

The selected runtime config must include a matching card:

```json
{
  "alias": "visa_3ds_success",
  "requires_3ds": true,
  "expected_otp": "000000"
}
```

For a real 100+ card catalogue, extend the private config file's `cards` array. Do not
commit real PAN, CVV, OTP, merchant tokens, API keys, secret keys, or callback URLs.
Local config copies under `examples/config/*.json` are ignored except checked-in
`*.example.json` templates.

Generate a synthetic private card dataset:

```bash
make synthetic-cards COUNT=100 OUT=/tmp/paynkolay-synthetic-cards.json
```

The output is a JSON array that can be copied into the selected environment's `cards`
field in a private `PAYNKOLAY_CONFIG_FILE`. The generator supports these profiles:

```bash
poetry run python tools/generate_synthetic_cards.py --count 100 --profile mixed --output /tmp/cards.json
poetry run python tools/generate_synthetic_cards.py --count 100 --profile three_ds --output /tmp/three-ds-cards.json
poetry run python tools/generate_synthetic_cards.py --count 100 --profile moto --output /tmp/moto-cards.json
```

Generate a matching large private scenario catalogue:

```bash
make synthetic-scenarios SCENARIO_COUNT=1000 SCENARIO_OUT=/tmp/paynkolay-synthetic-scenarios.json
```

The scenario generator writes a full catalogue object with a top-level `scenarios` array.
Generated scenario `card_alias` values rotate across generated card aliases, so pair
`SCENARIO_COUNT=1000` with `COUNT=100` by using `--card-count 100` when you want 100
cards to back 1000 scenarios:

```bash
poetry run python tools/generate_synthetic_scenarios.py --count 1000 --card-count 100 --output /tmp/scenarios.json
```

Supported scenario profiles are:

```bash
poetry run python tools/generate_synthetic_scenarios.py --count 1000 --profile mixed --output /tmp/scenarios.json
poetry run python tools/generate_synthetic_scenarios.py --count 1000 --profile three_ds --output /tmp/three-ds-scenarios.json
poetry run python tools/generate_synthetic_scenarios.py --count 1000 --profile moto --output /tmp/moto-scenarios.json
poetry run python tools/generate_synthetic_scenarios.py --count 1000 --profile negative --output /tmp/negative-scenarios.json
```

Run a generated or private scenario catalogue:

```bash
make scenarios-file SCENARIO_FILE=/tmp/paynkolay-synthetic-scenarios.json
```

This sets `PAYNKOLAY_SCENARIO_CATALOG` for the pytest process and runs the `scenario`
test group. Use `make parallel` for the default checked-in suite; for a private scenario
file, run the equivalent command directly with `pytest-xdist`:

```bash
PAYNKOLAY_SCENARIO_CATALOG=/tmp/paynkolay-synthetic-scenarios.json poetry run pytest -m scenario -n auto
```

Run the full generated-data demo with one command:

```bash
make scale-demo
```

This generates:

- `/tmp/paynkolay-synthetic-cards.json`
- `/tmp/paynkolay-synthetic-scenarios.json`

Then it executes the generated scenario catalogue through the mocked scenario flow. For
parallel execution, use:

```bash
make scale-demo-parallel
```

Both commands accept overrides:

```bash
make scale-demo COUNT=100 SCENARIO_COUNT=1000
make scale-demo-parallel COUNT=100 SCENARIO_COUNT=1000
```

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
- Sales `sx`.
- PaymentList `sx`, if different.
- Cancel/refund `sx`, if different.
- Merchant ID, terminal ID, and secret/hash key.
- HTTPS success URL reachable by Paynkolay.
- HTTPS fail URL reachable by Paynkolay.
- Callback URL and callback payload sample, if callback delivery is separate from
  success/fail redirects.
- Callback signature algorithm and field order.
- Test card catalogue, expected statuses, card types, banks, and 3DS OTP values.
- 3DS sandbox page selectors or documented challenge flow.
- Installment, MoTo, currency, capture, and detailed sandbox business rules.
- Confirmation that `RESPONSE_CODE=2` maps to `captured` or `authorized` for the selected
  Paynkolay flow.
- Cancel/refund timing and amount rules.

Before real calls, validate the private inputs:

```bash
export PAYNKOLAY_CONFIG_FILE=/path/outside/git/paynkolay-settings.json
export PAYNKOLAY_SCENARIO_CATALOG=/path/outside/git/sandbox-scenarios.json
make sandbox-ready
```

The readiness check expects the private catalogue to cover successful and negative 3DS,
MoTo success/failure, wrong OTP, invalid CVV, expired card, insufficient funds, debit,
credit, PaymentList verification, cancel/refund, and installment counts `2`, `3`, `6`,
`9`, and `12`.

## Safety Rules

Do not expose full PAN, CVV, OTP, API keys, secret keys, signatures, or tokens in logs or
reports. Use `paynkolay_pos.reporting.sanitize_evidence()` or
`attach_json_evidence()` before attaching payloads to Allure.
