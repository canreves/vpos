"""Provider result handling helpers for web return URLs."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from pydantic import SecretStr

from paynkolay_pos.models import PaynkolayPaymentResult


class PaymentResultHashVerificationError(ValueError):
    """Raised when a provider result hash is invalid."""


@dataclass(frozen=True)
class VerifiedPaymentResult:
    """Verified provider result plus browser-facing metadata."""

    result: PaynkolayPaymentResult

    @property
    def order_id(self) -> str:
        return self.result.client_reference_code

    @property
    def provider_transaction_id(self) -> str:
        return self.result.reference_code

    @property
    def failure_reason(self) -> str | None:
        if self.result.successful:
            return None
        return self.result.response_data or self.result.response_code


def provider_result_payload(raw_payload: Mapping[str, object]) -> dict[str, object]:
    """Normalize request form/query data into a plain provider result payload."""

    return {
        key: value
        for key, value in raw_payload.items()
        if isinstance(value, str | int | float)
    }


def verify_provider_payment_result(
    payload: Mapping[str, object],
    *,
    merchant_secret_key: SecretStr | str,
) -> VerifiedPaymentResult:
    """Parse and verify a Paynkolay success/fail URL result payload."""

    result = PaynkolayPaymentResult.model_validate(provider_result_payload(payload))
    if not result.verify_hash(merchant_secret_key):
        raise PaymentResultHashVerificationError("Paynkolay result hash verification failed")
    return VerifiedPaymentResult(result=result)
