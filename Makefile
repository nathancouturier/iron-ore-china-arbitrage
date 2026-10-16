# One-command rebuild. `make all` refreshes recent data and rebuilds the models, site and note
# (cross-source checks and the data audit keep their last full run); `make full` re-fetches every source.
PY ?= python
NODE ?= node

.PHONY: all full install ingest transform validate model export report audit test lint format site-check serve

all:
	$(PY) -m pipeline all
	$(MAKE) test lint site-check

full:
	$(PY) -m pipeline all --full
	$(MAKE) test lint site-check

install:
	$(PY) -m pip install -r requirements-dev.txt

ingest transform validate model export report audit:
	$(PY) -m pipeline $@

test:
	$(PY) -m pytest

lint:
	ruff check ironarb pipeline tests scripts
	ruff format --check ironarb pipeline tests scripts

format:
	ruff format ironarb pipeline tests scripts

site-check:
	$(PY) scripts/check_site.py

serve:
	$(PY) -m http.server 8000 --directory site
