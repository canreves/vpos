"""Paynkolay provider result models and verification helpers."""

from __future__ import annotations

from datetime import UTC, datetime, tzinfo
from decimal import Decimal
from enum import StrEnum

from pydantic import AliasChoices, Field, SecretStr
from pydantic.functional_validators import field_validator

from paynkolay_pos.models.payments import (
    Currency,
    PaymentStatus,
    StrictPaymentModel,
    TransactionStatusResponse,
)
from paynkolay_pos.security import generate_payment_response_hash


class PaynkolayProviderStatus(StrEnum):
    """Transaction status values returned by Paynkolay verification responses."""

    SUCCESS = "SUCCESS"
    ERROR = "ERROR"
    NEW = "NEW"


class PaynkolayCancelRefundType(StrEnum):
    """Operation types accepted by Paynkolay's cancel/refund service."""

    CANCEL = "cancel"
    REFUND = "refund"


class PaynkolayThreeDSInitializeResult(StrictPaymentModel):
    """Provider response containing an HTML form for a 3DS challenge."""

    bank_request_message: str = Field(alias="BANK_REQUEST_MESSAGE", min_length=1)

    @property
    def status(self) -> PaymentStatus:
        """3DS HTML means the payment is waiting for browser authentication."""

        return PaymentStatus.PENDING_3DS


class PaynkolayPaymentResult(StrictPaymentModel):
    """Success/fail URL payment result payload sent by Paynkolay."""

    response_code: str = Field(alias="RESPONSE_CODE", min_length=1)
    response_data: str | None = Field(default=None, alias="RESPONSE_DATA")
    use_3d: str = Field(alias="USE_3D", min_length=1)
    rnd: str = Field(alias="RND", min_length=1)
    merchant_no: str = Field(alias="MERCHANT_NO", min_length=1)
    auth_code: str = Field(default="", alias="AUTH_CODE")
    reference_code: str = Field(alias="REFERENCE_CODE", min_length=1)
    client_reference_code: str = Field(alias="CLIENT_REFERENCE_CODE", min_length=1)
    timestamp: str = Field(alias="TIMESTAMP", min_length=1)
    transaction_amount: Decimal = Field(alias="TRANSACTION_AMOUNT", gt=Decimal("0"))
    authorization_amount: Decimal = Field(alias="AUTHORIZATION_AMOUNT", gt=Decimal("0"))
    commission: Decimal | None = Field(default=None, alias="COMMISION")
    commission_rate: Decimal | None = Field(default=None, alias="COMMISION_RATE")
    installment: int = Field(alias="INSTALLMENT", ge=1)
    currency_code: Currency = Field(alias="CURRENCY_CODE")
    hash_data: str | None = Field(default=None, alias="hashData")
    hash_data_v2: str = Field(alias="hashDataV2", min_length=1)

    @field_validator("transaction_amount", "authorization_amount")
    @classmethod
    def normalize_amount(cls, amount: Decimal) -> Decimal:
        """Keep provider amount strings comparable with internal models."""

        return amount.quantize(Decimal("0.01"))

    @property
    def successful(self) -> bool:
        """Apply Paynkolay's documented payment success rule."""

        normalized_auth_code = self.auth_code.strip()
        return (
            self.response_code == "2"
            and normalized_auth_code not in {"", "0", "00"}
        )

    @property
    def status(self) -> PaymentStatus:
        """Map Paynkolay result fields to the internal payment status enum."""

        if self.successful:
            return PaymentStatus.CAPTURED
        return PaymentStatus.FAILED

    def expected_hash(self, merchant_secret_key: SecretStr | str) -> str:
        """Recalculate the documented response ``hashDataV2`` value."""

        return generate_payment_response_hash(
            merchant_no=self.merchant_no,
            reference_code=self.reference_code,
            auth_code=self.auth_code,
            response_code=self.response_code,
            use_3d=self.use_3d,
            rnd=self.rnd,
            installment=self.installment,
            authorization_amount=self.canonical_authorization_amount,
            currency_code=self.currency_code.value,
            merchant_secret_key=merchant_secret_key,
        )

    def verify_hash(self, merchant_secret_key: SecretStr | str) -> bool:
        """Return whether the provider result hash matches the payload."""

        return self.hash_data_v2 == self.expected_hash(merchant_secret_key)

    @property
    def canonical_authorization_amount(self) -> str:
        """Return the exact authorization amount string used in response hash checks."""

        return f"{self.authorization_amount:.2f}"

    def to_transaction_status_response(
        self,
        *,
        source_timezone: tzinfo = UTC,
    ) -> TransactionStatusResponse:
        """Convert a success/fail URL result into the framework status model."""

        payment_status = self.status
        authorization_code = self.auth_code.strip() or None
        return TransactionStatusResponse(
            order_id=self.client_reference_code,
            provider_transaction_id=self.reference_code,
            status=payment_status,
            amount=self.authorization_amount,
            currency=self.currency_code,
            updated_at=self._parsed_timestamp(source_timezone),
            authorization_code=(
                authorization_code
                if payment_status in {PaymentStatus.AUTHORIZED, PaymentStatus.CAPTURED}
                else None
            ),
            failure_code=self.response_code if payment_status is PaymentStatus.FAILED else None,
        )

    def _parsed_timestamp(self, source_timezone: tzinfo) -> datetime:
        parsed = datetime.fromisoformat(self.timestamp)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=source_timezone)
        return parsed


def parse_paynkolay_payment_result(
    payload: dict[str, object],
) -> PaynkolayThreeDSInitializeResult | PaynkolayPaymentResult:
    """Parse a Paynkolay payment response/result into a typed provider model."""

    if "BANK_REQUEST_MESSAGE" in payload:
        return PaynkolayThreeDSInitializeResult.model_validate(payload)
    return PaynkolayPaymentResult.model_validate(payload)


class PaynkolayPaymentListRow(StrictPaymentModel):
    """One transaction row returned by Paynkolay's PaymentList service."""

    reference_code: str = Field(alias="REFERENCE_CODE", min_length=1)
    auth_code: str = Field(default="", alias="AUTH_CODE")
    authorization_amount: Decimal = Field(alias="AUTHORIZATION_AMOUNT", gt=Decimal("0"))
    transaction_amount: Decimal | None = Field(default=None, alias="TRANSACTION_AMOUNT")
    client_reference_code: str = Field(alias="CLIENT_REFERENCE_CODE", min_length=1)
    status: PaynkolayProviderStatus = Field(alias="STATUS")
    transaction_type: str | None = Field(default=None, alias="TRANSACTION_TYPE")
    trx_date: str = Field(alias="TRX_DATE", min_length=1)
    card_holder_name: str | None = Field(default=None, alias="CARD_HOLDER_NAME")
    is_3d: bool | None = Field(default=None, alias="IS_3D")
    installment_count: int | None = Field(default=None, alias="INSTALLMENT_COUNT")
    description: str | None = Field(default=None, alias="DESCRIPTION")

    @field_validator("authorization_amount", "transaction_amount")
    @classmethod
    def normalize_optional_amount(cls, amount: Decimal | None) -> Decimal | None:
        """Keep provider amount strings comparable with internal models."""

        if amount is None:
            return None
        return amount.quantize(Decimal("0.01"))

    @property
    def payment_status(self) -> PaymentStatus:
        """Map Paynkolay list status values to internal payment states."""

        if self.status is PaynkolayProviderStatus.SUCCESS:
            return PaymentStatus.CAPTURED
        if self.status is PaynkolayProviderStatus.ERROR:
            return PaymentStatus.FAILED
        return PaymentStatus.CREATED

    def to_transaction_status_response(
        self,
        *,
        currency: Currency = Currency.TRY,
        source_timezone: tzinfo = UTC,
    ) -> TransactionStatusResponse:
        """Convert a provider list row into the framework status model."""

        payment_status = self.payment_status
        failure_code = None
        if payment_status is PaymentStatus.FAILED:
            failure_code = self.description or self.status.value
        return TransactionStatusResponse(
            order_id=self.client_reference_code,
            provider_transaction_id=self.reference_code,
            status=payment_status,
            amount=self.authorization_amount,
            currency=currency,
            updated_at=self._parsed_trx_date(source_timezone),
            authorization_code=self.auth_code.strip() or None,
            failure_code=failure_code,
        )

    def _parsed_trx_date(self, source_timezone: tzinfo) -> datetime:
        parsed = datetime.strptime(self.trx_date, "%d.%m.%Y %H:%M:%S")
        return parsed.replace(tzinfo=source_timezone)


class PaynkolayPaymentListResult(StrictPaymentModel):
    """Inner ``result`` object returned by Paynkolay's PaymentList service."""

    response_code: str = Field(alias="RESPONSE_CODE", min_length=1)
    response_data: str | None = Field(default=None, alias="RESPONSE_DATA")
    rows: tuple[PaynkolayPaymentListRow, ...] = Field(default=(), alias="LIST")

    @property
    def successful(self) -> bool:
        """Return whether the list service itself succeeded."""

        return self.response_code == "2"


class PaynkolayPaymentListResponse(StrictPaymentModel):
    """Typed response returned by Paynkolay's PaymentList verification service."""

    id: str | None = None
    result: PaynkolayPaymentListResult

    def rows_for_client_ref(self, client_ref_code: str) -> tuple[PaynkolayPaymentListRow, ...]:
        """Return all transaction rows matching a merchant client reference code."""

        return tuple(
            row for row in self.result.rows if row.client_reference_code == client_ref_code
        )


class PaynkolayCancelRefundResult(StrictPaymentModel):
    """Typed response returned by Paynkolay's cancel/refund service."""

    response_code: str = Field(
        validation_alias=AliasChoices("responseCode", "RESPONSE_CODE"),
        min_length=1,
    )
    response_data: str | None = Field(
        default=None,
        validation_alias=AliasChoices("responseData", "RESPONSE_DATA"),
    )
    transaction_type: PaynkolayCancelRefundType = Field(alias="type")

    @field_validator("response_code", mode="before")
    @classmethod
    def normalize_response_code(cls, response_code: object) -> str:
        """Accept provider response codes whether they arrive as text or numbers."""

        return str(response_code)

    @property
    def successful(self) -> bool:
        """Return whether the cancel/refund service reports success."""

        return self.response_code == "2"

    @property
    def status(self) -> PaymentStatus:
        """Map a successful operation to the internal final payment state."""

        if not self.successful:
            return PaymentStatus.FAILED
        if self.transaction_type is PaynkolayCancelRefundType.CANCEL:
            return PaymentStatus.CANCELLED
        return PaymentStatus.REFUNDED
