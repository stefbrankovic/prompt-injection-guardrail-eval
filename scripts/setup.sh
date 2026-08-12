#!/usr/bin/env bash
# =============================================================================
# KOMANDA ZA SETUP:  bash scripts/setup.sh
#
# Pravi conda env, instalira paket, pokrece testove i proveru pristupa.
# =============================================================================
set -euo pipefail

ENV_NAME="psiml"
cd "$(dirname "$0")/.."

echo "==> 1/5 conda okruzenje"
if conda env list | grep -qE "^${ENV_NAME}\s"; then
  echo "    '${ENV_NAME}' vec postoji, azuriram"
  conda env update -n "$ENV_NAME" -f environment.yml --prune
else
  conda env create -f environment.yml
fi

# shellcheck disable=SC1091
eval "$(conda shell.bash hook)"
conda activate "$ENV_NAME"

echo "==> 2/5 instaliram paket (editable)"sp
pip install -e . -q

echo "==> 3/5 nbstripout (sprecava merge konflikte u notebook-ovima)"
nbstripout --install --attributes .gitattributes 2>/dev/null || echo "    preskoceno"

echo "==> 4/5 testovi"
pytest -q

echo "==> 5/5 provera pristupa HF resursima"
python scripts/check_access.py || {
  echo
  echo "!!! Neki resursi nisu dostupni. Vidi poruke iznad."
  echo "!!! Za gated modele zatrazi pristup ODMAH (odobrenje traje par sati)."
}

cat <<'EOS'

==> Gotovo.

Sledece:
  conda activate psiml
  make demo          # demo napada, bez modela, radi odmah
  make baseline      # baseline detektora na engleskom (D1)
  cat docs/MEETING_2026-08-10.md    # priprema za sastanak sa Kristinom

Ako check_access javlja GATED:
  1) otvori link, klikni "Request access"
  2) `hf auth login` sa tokenom sa https://huggingface.co/settings/tokens
EOS
