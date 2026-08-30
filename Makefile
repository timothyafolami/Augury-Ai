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

# --extra experiments, because part of the suite runs the case experiments
# against the repositories they measure, and those import sqlalchemy. Without
# it a fresh clone fails twelve tests for a reason that has nothing to do with
# the code under test.
test:
	uv run --extra experiments pytest -q

fmt:
	uv run ruff check --fix src tests
	uv run ruff format src tests

# -- reviews and evaluation (need an API key; see docs/REPRODUCE.md) --------

.PHONY: review-baseline review-augury evaluate eval-replay record web serve

review-baseline:
	uv run python -m augury.cli review --arm baseline --case B01

review-augury:
	uv run python -m augury.cli review --arm augury --case B01

evaluate:
	uv run python -m augury.cli evaluate --seeds 5 --prove

# The path a judge takes. Serves every model call from the committed cassettes,
# never reaches the network, needs no API key, and spends nothing. It reports
# $0.00 because that is what this process spent; the costs in README.md were
# measured when the cassettes were recorded.
# Provider and model are pinned, not taken from .env: the model id is part of
# every cassette key, so replaying under a different one reproduces nothing.
# Switching AUGURY_PROVIDER in .env used to make every published number
# irreproducible, with an error that blamed missing recordings.
#
# --extra experiments for the same reason as `record`: a judge running this in
# a fresh clone has no sqlalchemy, and every experiment comes back Broken.
eval-replay:
	AUGURY_REPLAY_ONLY=1 AUGURY_PROVIDER=groq AUGURY_MODEL=openai/gpt-oss-120b \
	  uv run --extra experiments python -m augury.cli evaluate --seeds 5 --prove

# Re-record the cassettes. Needs a key and spends real money. Only necessary
# after a prompt, schema or model change, each of which correctly invalidates
# every recording that depended on it.
# --extra experiments, because the case experiments import the repository they
# measure and a plain `uv sync` installs no extras. Without it a clean clone
# reproduces the model calls and breaks every experiment, which is most of the
# published table.
# Pinned to the same model eval-replay asks for, so a recording made from a
# shell with a different .env cannot silently produce cassettes nothing can
# replay.
record:
	AUGURY_RECORD=1 AUGURY_PROVIDER=groq AUGURY_MODEL=openai/gpt-oss-120b \
	  uv run --extra experiments python -m augury.cli evaluate --seeds 5 --prove


# The web interface. A build is generated, so a clone does not have one and the
# server says so at / rather than serving a blank page.
web:
	cd web && npm install && npm run build

# One command for a demonstration: build the interface if it is missing, then
# serve it and the API from one process.
serve:
	@test -d web/dist || $(MAKE) web
	uv run python -m augury.server
