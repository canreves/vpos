.PHONY: help install check lint type test smoke api three-ds callback negative parallel allure-results report clean

PYTEST ?= poetry run pytest
RUFF ?= poetry run ruff check .
MYPY ?= poetry run mypy src tests
ALLURE_RESULTS ?= allure-results
ALLURE_REPORT ?= allure-report

help:
	@echo "Paynkolay Sanal POS automation commands"
	@echo ""
	@echo "Setup:"
	@echo "  make install         Install project dependencies with Poetry"
	@echo ""
	@echo "Validation:"
	@echo "  make check           Run poetry check, ruff, mypy, and pytest"
	@echo "  make lint            Run Ruff"
	@echo "  make type            Run mypy"
	@echo "  make test            Run the full pytest suite"
	@echo "  make parallel        Run the full pytest suite with pytest-xdist"
	@echo ""
	@echo "Focused tests:"
	@echo "  make smoke           Run smoke-marked tests"
	@echo "  make api             Run API-marked tests"
	@echo "  make three-ds        Run 3D Secure-marked tests"
	@echo "  make callback        Run callback-marked tests"
	@echo "  make negative        Run negative-marked tests"
	@echo ""
	@echo "Reporting:"
	@echo "  make allure-results  Run tests and write Allure result files"
	@echo "  make report          Generate an Allure HTML report"
	@echo ""
	@echo "Maintenance:"
	@echo "  make clean           Remove generated local artifacts"

install:
	poetry install --no-interaction

check:
	poetry check
	$(RUFF)
	$(MYPY)
	$(PYTEST)

lint:
	$(RUFF)

type:
	$(MYPY)

test:
	$(PYTEST)

parallel:
	$(PYTEST) -n auto

smoke:
	$(PYTEST) -m smoke

api:
	$(PYTEST) -m api

three-ds:
	$(PYTEST) -m three_ds

callback:
	$(PYTEST) -m callback

negative:
	$(PYTEST) -m negative

allure-results:
	rm -rf $(ALLURE_RESULTS)
	$(PYTEST) --alluredir=$(ALLURE_RESULTS)

report: allure-results
	@command -v allure >/dev/null 2>&1 || { echo "Allure CLI is required. Install it with: brew install allure"; exit 1; }
	allure generate $(ALLURE_RESULTS) -o $(ALLURE_REPORT) --clean

clean:
	find . -type d \( -name "__pycache__" -o -name ".pytest_cache" -o -name ".mypy_cache" -o -name ".ruff_cache" -o -name "allure-results" -o -name "allure-report" -o -name "reports" \) -prune -exec rm -rf {} +
