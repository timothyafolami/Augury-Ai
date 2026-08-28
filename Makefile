# One definition of green. CI runs `make check`; so do you.
.PHONY: install check lint types test fmt

install:
	uv sync --frozen --all-extras

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
