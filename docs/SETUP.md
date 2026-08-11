# SETUP — kompletno okruženje, korak po korak

Cilj: do kraja ovog dokumenta oboje imate isti repo koji radi, git uvežban, AgentDojo skinut, i `pytest` prolazi na oba laptopa. Uradite ovo **pre** bilo kakvog pravog posla.

Pretpostavka: Windows + VS Code + Anaconda (ako je neko na Linux/Mac, koraci su isti osim putanja).

---

## FAZA 0 — Alati (jednom, ako već nisu instalirani)

1. **VS Code** — https://code.visualstudio.com
2. **Anaconda** ili **Miniconda** — https://docs.conda.io/en/latest/miniconda.html (Miniconda je dovoljna i lakša)
3. **Git** — https://git-scm.com/download/win (uključuje Git Bash)
4. **VS Code ekstenzije** (Ctrl+Shift+X, instaliraj): `Python`, `Jupyter`, `GitLens` (opciono ali korisno)

---

## FAZA 1 — Uvezati Git Bash + conda u VS Code terminal

Ovo je deo koji obično zezne ljude na Windows-u. Cilj: da u VS Code terminalu možeš i `git` i `conda activate` da kucaš.

### 1a. Podesi Git Bash kao default terminal (opciono, ali prijatnije)
- VS Code → Ctrl+Shift+P → *"Terminal: Select Default Profile"* → izaberi **Git Bash**.

### 1b. Omogući conda u Git Bash-u
Git Bash podrazumevano ne zna za `conda`. Otvori Git Bash (ne VS Code) jednom i pokreni:

```bash
# prilagodi putanju ako je Anaconda negde drugde
source /c/Users/$USERNAME/anaconda3/etc/profile.d/conda.sh
conda init bash
```

Zatvori i otvori terminal. Sad `conda activate` radi u Git Bash-u.

**Ako koristiš Anaconda Prompt umesto Git Bash** (jednostavnije, bez gornjeg koraka): VS Code → Select Default Profile → *Command Prompt*, pa u njemu radi `conda`. Git komande i dalje rade jer je Git u PATH-u. Oba pristupa su ok — bitno je da u **jednom** terminalu imaš i git i conda.

### 1c. Provera
```bash
git --version        # git version 2.x
conda --version      # conda 24.x
```
Oba moraju da odgovore. Ako `conda` ne radi u Git Bash-u, koristi Anaconda Prompt.

---

## FAZA 2 — Klonirati repo i napraviti okruženje

### 2a. Stefan (prvi put, pravi repo na GitHub-u)
Ako repo još ne postoji na GitHub-u:
```bash
cd ~/psiml/psiml_project           # gde je bootstrap napravio repo
git remote add origin https://github.com/stefbrankovic/psiml_project.git
git branch -M main
git push -u origin main
```

### 2b. Katarina (klonira)
```bash
cd ~/                              # ili gde god hoće da drži projekat
git clone https://github.com/stefbrankovic/psiml_project.git
cd psiml_project
```

### 2c. Oboje — napravi okruženje (jedna komanda)
```bash
bash scripts/setup.sh
```
Ovo pravi conda env `psiml`, instalira paket, pokreće testove i proveru pristupa. Ako `bash` ne radi na Windows-u van Git Bash-a, pokreni ručno:
```bash
conda env create -f environment.yml
conda activate psiml
pip install -e .
pytest -q
```

### 2d. Izaberi Python interpreter u VS Code
- Ctrl+Shift+P → *"Python: Select Interpreter"* → izaberi onaj sa `psiml` u imenu.
- Sad kad otvoriš terminal u VS Code, trebalo bi automatski da aktivira `psiml`. Ako ne: `conda activate psiml`.

### 2e. Provera da sve radi
```bash
pytest -q                          # 9 passed
make demo                          # demo napada (ili: python -m psiml.cli.demo_attack)
make sanity                        # test detektora sa kontrolnom grupom
```

---

## FAZA 3 — HuggingFace pristup (POKRENUTI ODMAH, čeka se par sati)

```bash
python scripts/check_access.py
```

Za svaki model koji javi `GATED`:
1. Otvori link koji skripta ispiše (npr. https://huggingface.co/meta-llama/Llama-Prompt-Guard-2-86M)
2. Klikni **"Request access"** / **"Agree and access"**
3. Sačekaj email (obično par sati, ponekad odmah)

Zatim se uloguj:
```bash
pip install -U "huggingface_hub[cli]"
hf auth login                      # nalepi token sa https://huggingface.co/settings/tokens
```

Ponovi `python scripts/check_access.py` dok sve ne bude `OK`.

---

## FAZA 4 — AgentDojo

```bash
pip install "agentdojo[transformers]"
```

Provera da se importuje:
```bash
python -c "import agentdojo; print('AgentDojo OK', agentdojo.__version__)"
```

Brzi pregled šta ima unutra (za D1):
```bash
python -c "
from agentdojo.task_suite import load_suites
# pogledaj koje suite postoje i koliko taskova imaju
"
```
*(Tačan API proveriti u njihovom README-u — verzije se menjaju. Zato ćemo D1 pinovati verziju.)*

**Pinuj verziju odmah** da se ne lomi tokom nedelje:
```bash
pip freeze | grep -i agentdojo >> requirements-lock.txt
git add requirements-lock.txt && git commit -m "chore: pin agentdojo verzija"
```

---

## FAZA 5 — Uvežbati git workflow DOK NIJE VAŽNO

Ovo je najvažniji deo. Napravite namerni, beznačajni konflikt i rešite ga sad, ne u sredu u 23h.

### 5a. Oboje: napravite svoju granu i trivijalnu izmenu
```bash
# Stefan
git checkout main && git pull
git checkout -b stefan/test
echo "Stefan je bio ovde" >> docs/daily/proba.md
git add -A && git commit -m "test: stefan proba"

# Katarina (u isto vreme, na svom laptopu)
git checkout main && git pull
git checkout -b katarina/test
echo "Katarina je bila ovde" >> docs/daily/proba.md   # ISTI fajl namerno!
git add -A && git commit -m "test: katarina proba"
```

### 5b. Stefan merge-uje prvi
```bash
git checkout main
git merge --no-ff stefan/test
git push
```

### 5c. Katarina povlači i rešava konflikt
```bash
git checkout main
git pull                           # sad ima Stefanovu izmenu
git merge --no-ff katarina/test    # KONFLIKT na proba.md
```
Git će označiti konflikt u fajlu ovako:
```
<<<<<<< HEAD
Stefan je bio ovde
=======
Katarina je bila ovde
>>>>>>> katarina/test
```
Otvori fajl u VS Code (ima lepe dugmiće "Accept Both Changes"), obriši markere, ostavi oba reda, pa:
```bash
git add docs/daily/proba.md
git commit -m "merge: resen test konflikt"
git push
```

### 5d. Očisti probu
```bash
git rm docs/daily/proba.md && git commit -m "chore: obrisi probu" && git push
git branch -d stefan/test katarina/test        # svako svoju
```

**Ako ste ovo prošli — git vas više neće iznenaditi ove nedelje.** To je bila cela poenta.

---

## FAZA 6 — Finalna provera pred spavanje

Oboje, na svom laptopu:
```bash
conda activate psiml
git checkout main && git pull
pytest -q                          # 9 passed
python scripts/check_access.py     # koliko modela je OK (gated možda još čeka)
python scripts/detector_sanity.py --mock
```

Ako oba laptopa daju isto — spremni ste za D1.

---

## Šablon dnevnog toka (od D1 nadalje)

```bash
# ujutru
conda activate psiml
git checkout main && git pull
git checkout -b stefan/<danasnji-zadatak>

# rad... commit koliko hoćeš

# kad je nešto gotovo
pytest -q                          # mora da prođe
make sync                          # merge u main + push (radi testove sam)
```

Sinhronizacija u 13h i 20h, po 10 minuta. `main` uvek prolazi testove.

---

## Ako nešto zapne

| Simptom | Rešenje |
|---|---|
| `conda: command not found` u Git Bash | koristi Anaconda Prompt, ili uradi FAZU 1b |
| `pytest` ne nalazi `psiml` | `pip install -e .` iz korena repoa, i proveri interpreter u VS Code |
| gated model `403` | još čeka odobrenje, ili nisi `hf auth login` |
| `agentdojo` import puca | proveri da si u `psiml` env-u; reinstaliraj sa `[transformers]` |
| merge konflikt panika | ne paniči, otvori fajl u VS Code, dugmići gore rešavaju 90% |
| notebook pravi konflikt | `nbstripout` nije aktiviran — `nbstripout --install` |
