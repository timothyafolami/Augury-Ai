# One definition of green. CI runs `make check`; so do you.
.PHONY: install check lint types test fmt

install:
	uv sync --frozen --all-extras
	git config core.hooksPath .githooks

check: lint types test

lint:
	uv run ruff check src tests
	uv run ruff format --check src tests

types:
	uv run mypy src tests

test:
	uv run pytest -q

fmt:
	uv run ruff check --fix src tests
	uv run ruff format src tests

# -- reviews and evaluation (need an API key; see docs/REPRODUCE.md) --------

.PHONY: review-baseline review-augury evaluate

review-baseline:
	uv run python -m augury.cli review --arm baseline --case B01

review-augury:
	uv run python -m augury.cli review --arm augury --case B01

evaluate:
	uv run python -m augury.cli evaluate --seeds 5 --prove
