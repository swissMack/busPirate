# Everything you need, without remembering any of it.
.DEFAULT_GOAL := help
VENV := .venv
PY := $(VENV)/bin/python

.PHONY: help setup dash demo test ports lint clean

help:  ## show this help
	@grep -hE '^[a-z-]+:.*?## ' $(MAKEFILE_LIST) | \
	  awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[1m%-8s\033[0m %s\n", $$1, $$2}'

$(PY):
	python3 -m venv $(VENV)
	$(VENV)/bin/pip install --quiet --upgrade pip
	$(VENV)/bin/pip install --quiet -e ".[dev,web]"

setup: $(PY)  ## create .venv and install everything

dash: $(PY)  ## open the dashboard against a real Bus Pirate
	$(PY) -m buspirate dashboard

demo: $(PY)  ## open the dashboard against a simulated device (no hardware)
	$(PY) -m buspirate dashboard --demo

test: $(PY)  ## run the test suite
	$(PY) -m pytest -q

ports: $(PY)  ## list serial ports and flag the likely Bus Pirate
	$(PY) -m buspirate ports

clean:  ## remove the virtualenv and caches
	rm -rf $(VENV) .pytest_cache **/__pycache__
