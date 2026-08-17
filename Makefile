.PHONY: help data tracks defense analyze figures test clean

PY := python
export PYTHONPATH := src

DETS_ALL := deepset protectai_v2 promptguard2_86m promptguard2_22m
DETS_3   := deepset promptguard2_86m protectai_v2
DETS_2   := deepset promptguard2_86m

help:
	@echo "make data      - prepare datasets"
	@echo "make tracks    - run T1-T4 (the only steps that call the models)"
	@echo "make defense   - corrected detection policy + position control"
	@echo "make analyze   - corrected analysis, no model calls"
	@echo "make figures   - regenerate all figures"
	@echo "make test      - unit tests"
	@echo "make all       - everything, in order"

data:
	$(PY) scripts/f2_data.py agentdojo-benign
	$(PY) scripts/f2_data.py benign-goals
	$(PY) scripts/f2_data.py sr-corpus --n 300

tracks:
	$(PY) scripts/f2_t1_envelope.py --detectors $(DETS_ALL)
	$(PY) scripts/f2_t2_script.py   --detectors $(DETS_3) --limit 150
	$(PY) scripts/f2_t3_window.py   --detectors $(DETS_3) --n-carriers 40
	$(PY) scripts/f2_t4_external.py --detectors $(DETS_3)

defense:
	$(PY) scripts/f2_defense.py --detectors $(DETS_2) --embed 4000 --holdout
	$(PY) scripts/f2_defense.py --detectors $(DETS_2) --embed 0    --holdout

analyze:
	$(PY) scripts/f2_analyze.py t1
	$(PY) scripts/f2_analyze.py t2
	$(PY) scripts/f2_analyze.py t3
	$(PY) scripts/f2_analyze.py t4

figures:
	$(PY) scripts/f2_figs.py
	$(PY) scripts/f2_fig9.py

test:
	pytest -q

all: data tracks defense analyze figures

clean:
	rm -rf __pycache__ .pytest_cache
	find . -name "*.pyc" -delete