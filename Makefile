all: format check test

format: prettier black ruff

check: mypy pyright checkblack checkruff checkprettier

prettier:
	uv run ./node_modules/.bin/prettier --write .

black:
	uv run black .

ruff:
	uv run ruff check . --fix

mypy:
	uv run mypy .

pyright:
	uv run ./node_modules/.bin/pyright

checkblack:
	uv run black --check .

checkruff:
	uv run ruff check .

checkprettier:
	uv run ./node_modules/.bin/prettier --check .

test:
	PYTHONUNBUFFERED=1 \
	DEBUG=true \
	uv run pytest

install-pre-commit-hook:
	uv run pre-commit install

pre-commit:
	uv run pre-commit run --all-files

checkbundle:
	@echo "skipping checkbundle"
