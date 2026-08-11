# Precice za ceste komande. `make` bez argumenta prikazuje pomoc.
.PHONY: help setup test demo access baseline attack figures clean sync

help:
	@echo "make setup     - conda env + install + testovi + provera pristupa"
	@echo "make access    - proveri HF pristup (gated modeli!)"
	@echo "make test      - pytest"
	@echo "make demo      - demo napada (bez modela, radi odmah)"
	@echo "make sanity    - ISPRAVAN test detektora (sa kontrolnom grupom!)"
	@echo "make baseline  - D1: detektori na engleskom"
	@echo "make attack    - D2: CyrEvade po jeziku/pismu"
	@echo "make figures   - regenerisi sve figure iz results/raw"
	@echo "make sync      - merge tekuce grane u main (posle testova)"
	@echo "make clean     - obrisi cache"

setup:
	bash scripts/setup.sh

access:
	python scripts/check_access.py

test:
	pytest -q

demo:
	python -m psiml.cli.demo_attack

# Test detektora sa kontrolnom grupom bezopasnih tekstova.
# BEZ ovoga TPR ne znaci nista. Vidi docs/TEORIJA.md, Deo 5.
sanity:
	python scripts/detector_sanity.py --mock
	@echo ""
	@echo "Gore je MOCK. Za prave detektore:"
	@echo "  python scripts/detector_sanity.py -d protectai_v2"
	@echo "  python scripts/detector_sanity.py -d promptguard2_86m"

baseline:
	python -m psiml.cli.run --config configs/experiments/baseline_en.yaml

attack:
	python -m psiml.cli.run --config configs/experiments/cyrevade.yaml

figures:
	python -m psiml.viz.make_figures

# Merge tekuce grane u main tek ako testovi prolaze.
sync:
	@pytest -q && \
	BRANCH=$$(git rev-parse --abbrev-ref HEAD) && \
	if [ "$$BRANCH" = "main" ]; then echo "Vec si na main."; exit 0; fi && \
	git checkout main && git pull && \
	git merge --no-ff $$BRANCH && git push && \
	echo "Merged $$BRANCH -> main"

clean:
	find . -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache .ruff_cache
