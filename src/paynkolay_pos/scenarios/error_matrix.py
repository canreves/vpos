"""Loader for the CSV error test matrix used by the mock interceptor."""

from __future__ import annotations

import csv
from collections.abc import Mapping
from pathlib import Path

from pydantic import BaseModel, Field

from paynkolay_pos.models import PaymentStatus

DEFAULT_ERROR_MATRIX_PATH = (
    Path(__file__).parents[3] / "examples" / "scenarios" / "test_matrix_cases.csv"
)

EXPECTED_COLUMNS = (
    "scenario",
    "input_condition",
    "expected_status",
    "expected_error_code",
    "expected_error_message",
    "notes",
)


class ErrorMatrixCase(BaseModel):
    """One row of the error test matrix, mapping a trigger to an expected failure."""

    model_config = {"extra": "forbid", "str_strip_whitespace": True}

    scenario: str = Field(min_length=1, pattern=r"^[a-z0-9][a-z0-9_]*$")
    input_condition: str = Field(min_length=1)
    expected_status: PaymentStatus
    expected_error_code: str = Field(min_length=1)
    expected_error_message: str = Field(min_length=1)
    notes: str = ""


def load_error_matrix(
    path: str | Path = DEFAULT_ERROR_MATRIX_PATH,
) -> Mapping[str, ErrorMatrixCase]:
    """Load the CSV error matrix into a dict keyed by scenario name."""

    matrix_path = Path(path).expanduser()
    if not matrix_path.is_file():
        raise FileNotFoundError(f"error matrix file does not exist: {matrix_path}")

    with matrix_path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None or tuple(reader.fieldnames) != EXPECTED_COLUMNS:
            raise ValueError(
                f"error matrix columns must be {EXPECTED_COLUMNS}, got {reader.fieldnames}"
            )
        cases: dict[str, ErrorMatrixCase] = {}
        for row in reader:
            case = ErrorMatrixCase.model_validate(row)
            if case.scenario in cases:
                raise ValueError(f"duplicate scenario in error matrix: {case.scenario}")
            cases[case.scenario] = case

    if not cases:
        raise ValueError("error matrix must contain at least one scenario")
    return cases
