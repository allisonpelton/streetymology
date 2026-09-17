# The pipeline, in order. `make` builds everything free; nothing here spends
# money without being named explicitly.
#
# Stages are wired by the files they actually read and write, so re-running
# after a change rebuilds only what depends on it. The two fetch stages hit the
# network and are deliberately NOT rebuilt by a plain `make`: their inputs are
# other people's servers, and re-downloading is neither free nor idempotent.
#
#   make              measure -> context -> batch, from data already on disk
#   make fetch        re-download OSM and the assessor. Network.
#   make candidates   re-query Wikidata. Network, slow.
#   make lint test    ruff, then the suite
#   make map          GeoJSON for the web map, from an answers CSV
#
# Spending money is `run_batch`, which is not a target. It takes --yes and
# refuses several ways; read its docstring before using it.

PY  := .venv/bin/python
RUN := $(PY) -m streetymology

RAW     := data/raw
DERIVED := data/derived

.DEFAULT_GOAL := context
.PHONY: all fetch candidates lint test check map polygons clean-derived help

## --- free: recomputed from what is already on disk ---------------------------

$(DERIVED)/street_measures.json: $(RAW)/osm_ways_geom.json \
                                 $(RAW)/assessor_subdivisions.json \
                                 data/subdivisions.json
	$(RUN).measure_streets

$(DERIVED)/place_context.json: $(DERIVED)/street_measures.json \
                               $(DERIVED)/candidates.json
	$(RUN).build_context

context: $(DERIVED)/place_context.json

# Renders the prompts and prices them. Sends nothing.
batch: $(DERIVED)/place_context.json
	$(RUN).build_batch

all: context batch

## --- network: only when asked ------------------------------------------------

$(RAW)/osm_ways_geom.json:
	$(RUN).fetch_osm

$(RAW)/assessor_subdivisions.json:
	$(RUN).fetch_assessor

fetch:
	$(RUN).fetch_osm
	$(RUN).fetch_assessor

# Wikidata search for every core name, then the P31 filter. Hours, not minutes.
# candidates.json is a dependency of build_context but has no rule that fires
# automatically: regenerating it between building a batch and parsing one would
# silently move every candidate letter.
candidates:
	$(RUN).fetch_candidates
	$(RUN).filter_candidates

## --- checks ------------------------------------------------------------------

lint:
	.venv/bin/ruff check src/ tests/

test:
	$(PY) -m pytest -q

check: lint test

## --- output ------------------------------------------------------------------

# ANSWERS is the answers CSV to draw. Override it:
#   make map ANSWERS=data/artifacts/answers_rekeyed.csv
ANSWERS ?= data/artifacts/answers_rekeyed.csv

map:
	$(RUN).export_map $(ANSWERS)

polygons:
	$(RUN).export_polygons

## --- housekeeping ------------------------------------------------------------

# Only what recomputes in seconds. Never touches raw/, which is a download, or
# artifacts/, which holds the record of paid runs.
clean-derived:
	rm -f $(DERIVED)/street_measures.json $(DERIVED)/place_context.json

help:
	@grep -E '^[a-z-]+:' Makefile | grep -v '^help' | cut -d: -f1 | sort -u
