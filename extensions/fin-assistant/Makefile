# =============================================================================
# fin-assistant — development task runner
# =============================================================================
# Usage:
#   make test           run full test suite
#   make test-unit      unit tests only (fast, no DB setup)
#   make test-grading   grading logic tests only
#   make test-extract   signal extraction tests only
#   make test-scores    channel scoring tests only
#   make test-amc       AMC matching tests only
#   make lint           ruff code style check
#   make typecheck      mypy static type check
#   make ci             full pipeline: lint + typecheck + all tests
#   make test-report    tests + write summary to logs/test_report.txt

PYTHON      := /usr/bin/python3
PYTEST      := $(PYTHON) -m pytest
RUFF        := $(PYTHON) -m ruff
MYPY        := $(PYTHON) -m mypy
PYTEST_ARGS := -v --tb=short --no-header -q
REPORT_FILE := logs/test_report.txt

.PHONY: test test-unit test-grading test-extract test-scores test-amc \
        lint typecheck ci test-report install-dev help

# -- Full suite ---------------------------------------------------------------

test:
	@echo "=== Running full test suite ==="
	$(PYTEST) tests/ $(PYTEST_ARGS)

# -- Targeted suites ----------------------------------------------------------

test-unit:
	@echo "=== Unit tests (no I/O) ==="
	$(PYTEST) tests/test_extractor.py tests/test_grading.py tests/test_amc.py \
	          $(PYTEST_ARGS)

test-grading:
	@echo "=== Grading logic tests ==="
	$(PYTEST) tests/test_grading.py $(PYTEST_ARGS) -v

test-extract:
	@echo "=== Signal extraction tests ==="
	$(PYTEST) tests/test_extractor.py $(PYTEST_ARGS) -v

test-scores:
	@echo "=== Channel scoring tests ==="
	$(PYTEST) tests/test_channel_scores.py $(PYTEST_ARGS) -v

test-amc:
	@echo "=== AMC matching tests ==="
	$(PYTEST) tests/test_amc.py $(PYTEST_ARGS) -v

# -- Code quality -------------------------------------------------------------

lint:
	@echo "=== Ruff lint ==="
	$(RUFF) check . --select E,W,F --ignore E501 \
	        --exclude __pycache__,.git,store,logs || true

typecheck:
	@echo "=== Mypy type check ==="
	$(MYPY) signals/ reports/ learning/ enrichers/ \
	        --ignore-missing-imports --no-error-summary || true

# -- Full CI pipeline ---------------------------------------------------------

ci: lint typecheck test
	@echo "=== CI pipeline complete ==="

# -- Test report (machine-readable for Telegram notification) -----------------

test-report:
	@mkdir -p logs
	@echo "=== Generating test report ==="
	@$(PYTEST) tests/ $(PYTEST_ARGS) \
	    --tb=line \
	    2>&1 | tee $(REPORT_FILE)
	@echo "Report written to $(REPORT_FILE)"

# -- Dev dependencies ---------------------------------------------------------

install-dev:
	$(PYTHON) -m pip install pytest pytest-cov ruff mypy --quiet

# -- Help ---------------------------------------------------------------------

help:
	@echo ""
	@echo "fin-assistant test runner"
	@echo ""
	@echo "  make test           Full test suite"
	@echo "  make test-unit      Unit tests only (fast)"
	@echo "  make test-grading   Grading logic"
	@echo "  make test-extract   Signal extraction"
	@echo "  make test-scores    Channel scoring"
	@echo "  make test-amc       AMC matching"
	@echo "  make lint           Ruff style check"
	@echo "  make typecheck      Mypy type check"
	@echo "  make ci             Full pipeline"
	@echo "  make test-report    Tests + write report file"
	@echo ""
