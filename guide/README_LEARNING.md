# Paynkolay Sanal POS Automation and Test Framework - Learning Guide

## 0. Purpose of This Document

This project is not only a test automation repository. It is a learning path for understanding how a modern Sanal POS payment integration is tested with Python.

Before we write production or automation code, we need to align on three things:

1. **What fintech behavior we are testing**
2. **How the framework architecture will model that behavior**
3. **Why each Python tool is chosen for this type of payment system**

The goal is to build an automation framework that can validate API-based payment flows, 3D Secure browser flows, callback/webhook behavior, cryptographic signatures, negative scenarios, reporting, and parallel execution without turning the tests into fragile scripts.

---

## 1. Core Fintech Logic

### 1.1 What Is a Sanal POS Transaction?

A Sanal POS, or Virtual POS, is the online equivalent of a physical card terminal. Instead of inserting a card into a device, the merchant sends payment data to a payment provider API. The provider communicates with acquiring banks, card schemes, issuer banks, fraud systems, and sometimes 3D Secure authentication services.

At a high level, a card payment test usually validates this chain:

1. The merchant application prepares a payment request.
2. The request is sent to the Sanal POS API.
3. The payment provider validates merchant credentials, card data, amount, currency, order identity, and security signature.
4. If the transaction requires 3D Secure, the API returns a browser redirection target.
5. The shopper completes issuer authentication in a browser-like page.
6. The payment provider receives the 3DS result.
7. The merchant receives a callback or webhook.
8. The merchant queries or verifies final transaction status.

The automation framework needs to test this as a distributed workflow, not as a single HTTP call.

### 1.2 Typical Transaction States

Payment systems are state machines. A transaction moves through states, and tests should assert those states explicitly.

Common states include:

- `created`: The merchant has prepared an order or payment intent.
- `pending_3ds`: The provider requires browser-based cardholder authentication.
- `authenticated`: 3D Secure authentication succeeded.
- `authorized`: The issuer approved holding the amount.
- `captured`: The merchant captured the authorized amount.
- `failed`: The transaction was rejected, timed out, or failed validation.
- `cancelled`: The authorization was voided before capture.
- `refunded`: Funds were returned after settlement or capture.

The important engineering lesson is that a payment test should not only check HTTP `200`. It should check business state, amount integrity, currency integrity, order identity, signature validity, and final provider status.

### 1.3 What Happens During 3D Secure Browser Redirection?

3D Secure is an authentication layer designed to prove that the cardholder is really participating in the transaction.

In a simplified 3DS flow:

1. The merchant sends a payment initialization request.
2. The Sanal POS API decides the transaction requires 3DS.
3. The API returns one of the following:
   - an HTML form,
   - a redirect URL,
   - an ACS challenge URL,
   - or provider-specific fields needed to continue authentication.
4. The browser is redirected to the 3DS authentication page.
5. The cardholder enters an OTP, password, biometric confirmation, or test challenge value.
6. The issuer or Access Control Server sends the result back through the payment flow.
7. The provider finalizes the transaction and notifies the merchant.

From an automation perspective, this is where API testing alone is insufficient. We need browser automation because part of the transaction moves from server-to-server HTTP into a browser challenge.

That is why this project will use **Playwright Python**. It allows us to:

- open the 3DS redirect target,
- detect the OTP input form,
- inject test OTP values,
- submit the challenge,
- wait for navigation or callback confirmation,
- capture screenshots and traces for debugging.

The core learning point is that 3DS tests are hybrid tests: part API automation, part browser automation, part asynchronous state verification.

### 1.4 How a Callback or Webhook Works

A callback or webhook is a server-to-server notification sent by the payment provider to the merchant system.

The key difference:

- A **browser redirect** tells the shopper's browser where to go.
- A **callback/webhook** tells the merchant backend what happened.

In payment testing, the callback is critical because the browser result alone is not enough. Users can close tabs, lose network connection, or refresh pages. The merchant backend must rely on verified provider notifications and status queries.

A callback usually contains fields such as:

- merchant order ID,
- provider transaction ID,
- amount,
- currency,
- status,
- authorization code,
- failure reason,
- timestamp,
- signature or hash.

The framework will need a callback receiver or callback simulator depending on the environment. The test should verify:

1. The callback was received.
2. The callback belongs to the correct order.
3. The callback amount and currency match the original request.
4. The callback signature is valid.
5. The final transaction query agrees with the callback result.

The engineering lesson: callbacks are asynchronous. Tests must not assume immediate consistency. They need polling, timeout control, idempotency checks, and clear failure diagnostics.

### 1.5 How Cryptographic Hashing and Signatures Protect Payment Payloads

Payment APIs often require a hash or signature to prove that the request was created by a trusted merchant and was not modified in transit.

The common pattern is:

1. Select specific fields from the request.
2. Concatenate them in an exact provider-defined order.
3. Add a merchant secret, salt, or private key.
4. Calculate a hash or HMAC.
5. Send the result as a request field or header.

Example concept:

```text
signature_input = merchant_id + order_id + amount + currency + secret_key
signature = SHA256(signature_input)
```

Many real systems use HMAC instead of plain hashing:

```text
signature = HMAC_SHA256(secret_key, canonical_payload)
```

The important logic:

- A hash is deterministic: the same input always creates the same output.
- A tiny change in amount, order ID, or secret produces a completely different signature.
- The provider recalculates the signature on its side.
- If the signatures differ, the request is rejected.

Tests should include both positive and negative signature cases:

- valid signature,
- wrong secret,
- modified amount after signature creation,
- missing required field,
- incorrect field ordering,
- wrong encoding,
- timestamp outside allowed tolerance.

The learning point is that payment security bugs often happen in small details: string ordering, decimal formatting, character encoding, timezone handling, and secret management.

---

## 2. Architectural Decisions and Python Tech Stack

### 2.1 Python 3.11+ with Poetry

We will use **Python 3.11+** because it provides strong performance, mature async support, improved typing features, and excellent ecosystem support for test automation.

We will use **Poetry** for dependency and environment management.

Why Poetry:
- It creates isolated virtual environments.
- It locks dependency versions in `poetry.lock`.
- It separates runtime and development dependencies.
- It makes local setup reproducible for QA engineers, developers, and CI agents.

Java comparison:
- Poetry plays a similar role to Maven or Gradle dependency management.
- The Python environment is lighter, but it requires discipline around lock files and virtual environments.

### 2.2 Pytest and Data-Driven Testing

We will use **pytest** as the core test runner.

Pytest is chosen because it is simple at the surface but powerful for enterprise testing:

- fixtures for shared setup,
- markers for categorization,
- parameterization for data-driven scenarios,
- plugins for reporting and parallel execution,
- readable assertions with detailed failure output.

The key feature for payment scenario coverage is `@pytest.mark.parametrize`.

Instead of writing many duplicated tests:

```text
test_successful_payment_with_card_a
test_successful_payment_with_card_b
test_declined_payment_with_card_c
```

we model the cases as data:

```text
card, amount, currency, expected_status
```

Then the same test logic runs across many payment examples.

Java comparison:

- This is similar to TestNG `@DataProvider`.
- Pytest's style is usually more concise and combines naturally with fixtures.

The learning point: payment automation should separate **test logic** from **test data**. This makes it easier to add card scenarios, currencies, installment cases, and bank-specific rules.

### 2.3 pytest-xdist for Parallel Execution

Payment test suites can become slow because they involve network calls, browser automation, callbacks, and polling. **pytest-xdist** lets us run tests concurrently.

However, parallel execution introduces real risks:

- two tests using the same `order_id`,
- shared test cards being rate-limited,
- callbacks being matched to the wrong test,
- shared files being overwritten,
- test data cleanup racing with active tests.

To prevent race conditions, the framework must use:

- unique order IDs per test,
- isolated test state,
- correlation IDs,
- worker-safe temporary directories,
- no shared mutable global state,
- deterministic callback matching.

The learning point: parallelization is not just "run faster." It forces better architecture because every test must be independently identifiable and independently verifiable.

### 2.4 HTTPX Async for API Networking

We will use **HTTPX Async** for API calls.

Why HTTPX:

- It supports async and sync clients.
- It has a clean API similar to Python `requests`.
- It supports timeouts, connection pooling, headers, cookies, redirects, and structured clients.
- It works well with pytest async plugins.

Why async matters:

Payment flows often require waiting for external systems. With async IO, Python can wait on network responses without blocking the whole process.

Java comparison:

- RestAssured is excellent for Java API testing.
- HTTPX fills the Python role for clean HTTP clients, while async support gives us efficient concurrent network behavior.

The learning point: API test code should model real network behavior with explicit timeouts, retries where appropriate, and structured error handling. Silent indefinite waits are unacceptable in payment automation.

### 2.5 Playwright Python for 3DS Automation

We will use **Playwright Python** for browser automation.

Why Playwright:

- reliable browser automation,
- first-class async support,
- auto-waiting for elements and navigation,
- screenshots, videos, traces,
- Chromium, Firefox, and WebKit support,
- strong CI compatibility.

In this project, Playwright is specifically used for 3D Secure challenge handling:

- follow redirect URLs,
- fill OTP fields,
- submit issuer challenge pages,
- wait for final redirects,
- collect browser evidence for Allure reports.

The learning point: browser automation should be used only where the browser is part of the actual payment flow. API assertions should still verify the final transaction state.

### 2.6 Pydantic v2 for Runtime Type Safety

Payment payloads are structured data. Amounts, currencies, IDs, timestamps, callback fields, and signatures all have strict rules.

We will use **Pydantic v2** to define request and response models.

Why Pydantic:

- validates incoming and outgoing data,
- parses JSON into typed Python objects,
- catches missing or malformed fields early,
- supports custom validators,
- makes test failures easier to diagnose.

Java comparison:

- Pydantic models play a role similar to Jackson POJOs plus validation annotations.
- Unlike plain dictionaries, Pydantic gives runtime guarantees about field presence and shape.

The learning point: fintech tests should fail clearly when data is malformed. A vague `KeyError` is weak feedback; a validation error saying `amount must be greater than zero` is useful feedback.

### 2.7 Allure-Python for Enterprise Reporting

Payment test failures need evidence. A failed test should answer:

- Which order failed?
- Which provider transaction ID was involved?
- What request was sent?
- What response was returned?
- Was 3DS completed?
- Was the callback received?
- Was the signature valid?
- Which screenshot or trace proves the browser state?

We will use **Allure-Python** to produce structured reports.

Allure lets us attach:

- sanitized request and response payloads,
- screenshots,
- Playwright traces,
- callback bodies,
- computed signature inputs without secrets,
- step-by-step execution details.

The learning point: enterprise automation is not only about pass/fail. It is about producing enough evidence that engineers can quickly understand and fix failures.

---

## 3. Proposed Framework Architecture

The framework will be organized around clear boundaries:

```text
tests/
  api/
  e2e/
  contract/
src/
  config/
  clients/
  models/
  security/
  flows/
  callbacks/
  reporting/
  utils/
```

### 3.1 Layer Responsibilities

`config/`

Stores environment-specific settings such as base URLs, merchant IDs, callback URLs, timeouts, and feature flags. Secrets should come from environment variables or CI secret storage, not committed files.

`clients/`

Contains HTTPX API clients. These classes know how to send requests but should not contain test assertions.

`models/`

Contains Pydantic request and response models. These define the shape of payment initialization, status query, callback payloads, and error responses.

`security/`

Contains hashing, HMAC, canonicalization, and signature verification logic.

`flows/`

Contains higher-level business workflows such as `initialize_payment`, `complete_3ds`, `wait_for_callback`, and `verify_final_status`.

`callbacks/`

Contains callback receiver, callback storage, or callback matching helpers depending on the test environment.

`reporting/`

Contains Allure helpers that attach sanitized evidence.

`tests/`

Contains the actual test cases. Tests should read like business scenarios, not low-level HTTP scripts.

---

## 4. Step-by-Step Roadmap

### Phase 1 - Foundation and Project Skeleton

Learning goals:

- Understand Python project structure.
- Understand Poetry dependency management.
- Understand pytest fixtures and test discovery.
- Establish code style and configuration.

Implementation milestones:

1. Create `pyproject.toml` with Python 3.11+ and Poetry configuration.
2. Add dependencies: `pytest`, `pytest-asyncio`, `httpx`, `pydantic`, `playwright`, `allure-pytest`, and `pytest-xdist`.
3. Define base folders: `src/`, `tests/`, `config/`, and `reports/`.
4. Add initial pytest configuration and markers.
5. Add a smoke test that verifies the test runner is wired correctly.

Why this comes first:

Before modeling payments, we need a reproducible environment. Good automation frameworks fail early if the local environment or CI setup is inconsistent.

### Phase 2 - API Client, Models, and Signature Logic

Learning goals:

- Understand payment request structure.
- Understand Pydantic validation.
- Understand signature canonicalization.
- Understand negative security testing.

Implementation milestones:

1. Define Pydantic models for payment initialization requests and responses.
2. Define Pydantic models for transaction status responses.
3. Implement signature generation in a dedicated security module.
4. Implement signature verification for callbacks.
5. Build an HTTPX async client for Paynkolay API endpoints.
6. Write unit tests for hashing and canonicalization.
7. Write API tests for successful and invalid payment initialization.

Why this phase matters:

Most payment defects are not browser problems. They are payload, signature, amount, environment, or state-management problems. This phase gives us a reliable core.

### Phase 3 - 3D Secure Browser Flow and Callback Handling

Learning goals:

- Understand hybrid API and browser automation.
- Understand asynchronous callbacks.
- Understand polling, timeouts, and correlation IDs.
- Understand browser evidence collection.

Implementation milestones:

1. Add Playwright browser fixture.
2. Implement a 3DS flow helper that follows redirect URLs.
3. Automate OTP entry for test-bank challenge pages.
4. Capture screenshots and traces on success and failure.
5. Implement callback receiver or callback polling strategy.
6. Match callbacks to tests using unique order IDs or correlation IDs.
7. Verify callback signature and final transaction state.

Why this phase matters:

3DS is where many payment test frameworks become flaky. The correct approach is to separate browser mechanics from payment assertions and to treat callbacks as asynchronous events.

### Phase 4 - Enterprise-Grade Test Suite, Parallelism, and Reporting

Learning goals:

- Understand data-driven test design.
- Understand parallel execution safety.
- Understand reporting and observability.
- Understand CI readiness.

Implementation milestones:

1. Add parameterized tests for card scenarios, currencies, amounts, and expected outcomes.
2. Add pytest markers such as `smoke`, `regression`, `3ds`, `negative`, and `callback`.
3. Enable pytest-xdist execution.
4. Ensure every test creates unique order IDs.
5. Add Allure steps and sanitized attachments.
6. Add retry or polling helpers only where business behavior is eventually consistent.
7. Add CI command examples for smoke, regression, and parallel test runs.
8. Document known test cards, expected statuses, and environment setup.

Why this phase matters:

A test framework becomes valuable when it is reliable under real CI pressure. Parallel execution, clean evidence, and stable test data design are what make it usable by a team.

---

## 5. Design Principles We Will Follow

### 5.1 Business-Readable Tests

Tests should express payment behavior:

```text
Given a valid 3DS card
When the payment is initialized and the OTP challenge is completed
Then the transaction should be approved and the callback signature should be valid
```

The test body should not be cluttered with raw hashing details, HTTP header construction, or browser locator noise.

### 5.2 Strict State Isolation

Every test must own its own:

- order ID,
- correlation ID,
- callback matching key,
- temporary browser artifacts,
- report attachments.

This is required for safe parallel execution.

### 5.3 Security-Aware Logging

Reports must be useful without leaking secrets.

We can attach:

- masked card numbers,
- order IDs,
- transaction IDs,
- sanitized payloads,
- signature algorithm names.

We must not attach:

- full PAN values,
- CVV,
- merchant secret keys,
- raw OTPs,
- private credentials.

### 5.4 Deterministic Failure Messages

When a test fails, it should explain the exact broken expectation:

- expected callback status was `approved`, actual was `declined`,
- expected amount was `100.00`, actual was `10.00`,
- callback signature verification failed,
- transaction did not reach final state within 60 seconds.

Payment debugging is expensive. Clear failures reduce investigation time.

---

## 6. What We Will Do Next

After this learning document is reviewed, the next implementation step is Phase 1:

1. Create the Poetry project configuration.
2. Add the Python dependencies.
3. Configure pytest markers.
4. Create the initial source and test folder structure.
5. Add the first minimal smoke test.

Only after the foundation is stable will we move into payment models, hashing, API clients, 3D Secure automation, callback verification, parallel execution, and Allure reporting.

