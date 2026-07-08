"""Reusable test data builders for payment automation scenarios."""

from paynkolay_pos.testing.credential_matrix import (
    CredentialCardMatrixItem,
    CredentialErrorMatrixItem,
    build_credential_matrix_json,
    build_credential_matrix_payload,
    build_credential_runtime_config_json,
    build_credential_runtime_config_payload,
    build_credential_scenario_catalog_json,
    build_credential_scenario_catalog_payload,
)
from paynkolay_pos.testing.factories import (
    callback_payload,
    callback_payload_model,
    payment_card_payload,
    payment_initialize_request,
    payment_initialize_request_payload,
    signed_callback_payload,
    signed_callback_payload_model,
    transaction_status_response,
    transaction_status_response_payload,
)
from paynkolay_pos.testing.synthetic_cards import (
    SyntheticCardProfile,
    generate_synthetic_card_payloads,
    generate_synthetic_cards_json,
    validate_synthetic_card_payloads,
)
from paynkolay_pos.testing.synthetic_scenarios import (
    SyntheticScenarioProfile,
    generate_synthetic_scenario_catalog_json,
    generate_synthetic_scenario_catalog_payload,
    generate_synthetic_scenario_payloads,
    validate_synthetic_scenario_catalog,
)

__all__ = [
    "SyntheticCardProfile",
    "SyntheticScenarioProfile",
    "CredentialCardMatrixItem",
    "CredentialErrorMatrixItem",
    "build_credential_matrix_json",
    "build_credential_matrix_payload",
    "build_credential_runtime_config_json",
    "build_credential_runtime_config_payload",
    "build_credential_scenario_catalog_json",
    "build_credential_scenario_catalog_payload",
    "callback_payload",
    "callback_payload_model",
    "generate_synthetic_card_payloads",
    "generate_synthetic_cards_json",
    "generate_synthetic_scenario_catalog_json",
    "generate_synthetic_scenario_catalog_payload",
    "generate_synthetic_scenario_payloads",
    "payment_card_payload",
    "payment_initialize_request",
    "payment_initialize_request_payload",
    "signed_callback_payload",
    "signed_callback_payload_model",
    "transaction_status_response",
    "transaction_status_response_payload",
    "validate_synthetic_card_payloads",
    "validate_synthetic_scenario_catalog",
]
