.PHONY: help mp-check test-mp test-all

help:
	@echo "Available targets:"
	@echo "  mp-check     - Run multiprocessing consistency checks"
	@echo "  test-mp      - Run multiprocessing consistency tests"
	@echo "  test-all     - Run all tests"

mp-check:
	@echo "Running multiprocessing consistency checks..."
	@bash scripts/mp_consistency_check.sh
	@echo ""
	@echo "Running multiprocessing consistency tests..."
	@python -m pytest tests/test_multiprocessing_consistency.py -v

test-mp:
	@echo "Running multiprocessing consistency tests..."
	@python -m pytest tests/test_multiprocessing_consistency.py -v

test-all:
	@echo "Running all tests..."
	@python -m pytest tests/ -v
