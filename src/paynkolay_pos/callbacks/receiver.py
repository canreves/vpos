"""HTTP callback receiver skeleton for real sandbox end-to-end tests."""

from __future__ import annotations

import json
import os
from argparse import ArgumentParser
from collections.abc import Mapping, Sequence
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import ClassVar

from pydantic import SecretStr, ValidationError

from paynkolay_pos.callbacks.store import CallbackStore
from paynkolay_pos.callbacks.verifier import require_valid_callback_signature
from paynkolay_pos.models import CallbackPayload
from paynkolay_pos.reporting import sanitize_evidence
from paynkolay_pos.security import SignatureAlgorithm

DEFAULT_CALLBACK_PATH = "/callbacks/paynkolay"


class CallbackReceiverError(ValueError):
    """Raised when an inbound callback cannot be accepted."""


def accept_callback_payload(
    payload: Mapping[str, object],
    *,
    store: CallbackStore,
    secret_key: SecretStr | str,
    algorithm: SignatureAlgorithm = SignatureAlgorithm.HMAC_SHA256,
) -> CallbackPayload:
    """Validate, verify, and store one provider callback payload."""

    try:
        callback = CallbackPayload.model_validate(dict(payload))
    except ValidationError as exc:
        raise CallbackReceiverError("callback payload failed schema validation") from exc

    try:
        require_valid_callback_signature(
            callback,
            secret_key=secret_key,
            algorithm=algorithm,
        )
    except ValueError as exc:
        raise CallbackReceiverError("callback signature verification failed") from exc

    store.add(callback)
    return callback


def decode_callback_json(body: bytes) -> dict[str, object]:
    """Decode a callback request body into a JSON object."""

    try:
        decoded = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CallbackReceiverError("callback body must be valid UTF-8 JSON") from exc
    if not isinstance(decoded, dict):
        raise CallbackReceiverError("callback body must be a JSON object")
    return decoded


class CallbackReceiverHandler(BaseHTTPRequestHandler):
    """Minimal HTTP handler for sandbox callback capture."""

    callback_store: ClassVar[CallbackStore] = CallbackStore()
    secret_key: ClassVar[SecretStr | str] = ""
    algorithm: ClassVar[SignatureAlgorithm] = SignatureAlgorithm.HMAC_SHA256
    callback_path: ClassVar[str] = DEFAULT_CALLBACK_PATH

    def do_POST(self) -> None:
        """Accept Paynkolay callback POSTs."""

        if self.path != self.callback_path:
            self._write_json(
                HTTPStatus.NOT_FOUND,
                {"accepted": False, "error": "unknown callback path"},
            )
            return

        content_length = self.headers.get("Content-Length")
        if content_length is None:
            self._write_json(
                HTTPStatus.LENGTH_REQUIRED,
                {"accepted": False, "error": "missing content length"},
            )
            return

        try:
            body = self.rfile.read(int(content_length))
            payload = decode_callback_json(body)
            callback = accept_callback_payload(
                payload,
                store=self.callback_store,
                secret_key=self.secret_key,
                algorithm=self.algorithm,
            )
        except (CallbackReceiverError, ValueError) as exc:
            self._write_json(
                HTTPStatus.BAD_REQUEST,
                {"accepted": False, "error": str(exc)},
            )
            return

        self._write_json(
            HTTPStatus.ACCEPTED,
            {
                "accepted": True,
                "callback": sanitize_evidence(callback),
            },
        )

    def log_message(self, format: str, *args: object) -> None:
        """Silence default stderr logging; tests and runners own diagnostics."""

    def _write_json(self, status: HTTPStatus, payload: Mapping[str, object]) -> None:
        encoded = json.dumps(
            sanitize_evidence(payload),
            ensure_ascii=False,
            sort_keys=True,
        ).encode("utf-8")
        self.send_response(status.value)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


def create_callback_handler(
    *,
    store: CallbackStore,
    secret_key: SecretStr | str,
    algorithm: SignatureAlgorithm = SignatureAlgorithm.HMAC_SHA256,
    callback_path: str = DEFAULT_CALLBACK_PATH,
) -> type[CallbackReceiverHandler]:
    """Create a configured handler class for ``ThreadingHTTPServer``."""

    if not callback_path.startswith("/"):
        raise ValueError("callback_path must start with /")

    configured_store = store
    configured_secret_key = secret_key
    configured_algorithm = algorithm
    configured_callback_path = callback_path

    class ConfiguredCallbackReceiverHandler(CallbackReceiverHandler):
        callback_store = configured_store
        secret_key = configured_secret_key
        algorithm = configured_algorithm
        callback_path = configured_callback_path

    return ConfiguredCallbackReceiverHandler


def create_callback_server(
    *,
    host: str,
    port: int,
    store: CallbackStore,
    secret_key: SecretStr | str,
    algorithm: SignatureAlgorithm = SignatureAlgorithm.HMAC_SHA256,
    callback_path: str = DEFAULT_CALLBACK_PATH,
) -> ThreadingHTTPServer:
    """Create a local callback server ready for sandbox E2E tests."""

    handler = create_callback_handler(
        store=store,
        secret_key=secret_key,
        algorithm=algorithm,
        callback_path=callback_path,
    )
    return ThreadingHTTPServer((host, port), handler)


def main(argv: Sequence[str] | None = None) -> int:
    """Run a local callback receiver for manual sandbox testing."""

    parser = ArgumentParser(description="Run a local Paynkolay callback receiver")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8081)
    parser.add_argument("--path", default=DEFAULT_CALLBACK_PATH)
    parser.add_argument(
        "--secret-env",
        default="PAYNKOLAY_CALLBACK_SECRET",
        help="environment variable that contains the callback verification secret",
    )
    args = parser.parse_args(argv)

    secret_key = os.getenv(args.secret_env)
    if not secret_key:
        parser.error(f"{args.secret_env} must be set")

    store = CallbackStore()
    server = create_callback_server(
        host=args.host,
        port=args.port,
        store=store,
        secret_key=secret_key,
        callback_path=args.path,
    )
    print(f"listening on http://{args.host}:{args.port}{args.path}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return 0
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
