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
- Merchant ID, terminal ID, API key, optional cancel/refund API key, and secret/hash key.
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

Most local `guide/` notes remain ignored by Git. Checked-in guide files are intentional
handoff documentation and must not contain private credentials or real card data.
