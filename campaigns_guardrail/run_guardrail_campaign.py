#!/usr/bin/env python3
"""Dispatcher commun des campagnes ASI0x - DefenseClaw.

Lance une ou plusieurs campagnes (chacune un `run.py` autonome dans son propre
dossier `asiXX/`) comme sous-processus, puis affiche un recapitulatif global
colore. Chaque campagne garde son propre contrat (voir README) ; ce
dispatcher se contente d'orchestrer l'execution et d'agreger les codes retour.

Usage :
    cd /chemin/vers/OpenClawSecure && python3 campaigns/run_guardrail_campaign.py
    cd /chemin/vers/OpenClawSecure && python3 campaigns/run_guardrail_campaign.py asi01 asi03
    cd /chemin/vers/OpenClawSecure && python3 campaigns/run_guardrail_campaign.py --list

Toujours depuis la racine du depot (memes chemins que chaque run.py appele
individuellement) : c'est le repertoire courant qui determine ou chaque
campagne va chercher son dossier `campaigns/asiXX`.
"""

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import banner, bold, dim, status, summary_line, table  # noqa: E402

REPO_ROOT = Path.cwd()
CAMPAIGNS_DIR = Path(__file__).resolve().parent


def discover_campaigns():
    """Liste les campagnes disponibles : dossiers `asiXX/` avec un run.py non vide."""
    found = []
    for run_py in sorted(CAMPAIGNS_DIR.glob("asi*/run.py")):
        if run_py.stat().st_size > 0:
            found.append(run_py.parent.name)
    return found


def run_one(name):
    script = CAMPAIGNS_DIR / name / "run.py"
    print(bold(f"--- {name} ---"), flush=True)
    proc = subprocess.run([sys.executable, str(script)], cwd=REPO_ROOT)
    print()
    return proc.returncode


def main():
    available = discover_campaigns()
    if not available:
        print("Aucune campagne trouvee (aucun asiXX/run.py non vide).", file=sys.stderr)
        return 2

    args = sys.argv[1:]
    if args == ["--list"]:
        print("Campagnes disponibles : " + ", ".join(available))
        return 0

    requested = args or available
    unknown = [c for c in requested if c not in available]
    if unknown:
        print(f"Campagne(s) inconnue(s) : {', '.join(unknown)}", file=sys.stderr)
        print(f"Disponibles : {', '.join(available)}", file=sys.stderr)
        return 2

    banner(f"Campagnes ASI0x - {len(requested)} campagne(s)")
    print(dim(f"Repertoire d'execution : {REPO_ROOT}") + "\n", flush=True)

    outcomes = [(name, run_one(name)) for name in requested]

    rows = [
        [status(code == 0), name, "0" if code == 0 else str(code)]
        for name, code in outcomes
    ]
    table(["Statut", "Campagne", "Code retour"], rows)
    print()
    ok = sum(1 for _, code in outcomes if code == 0)
    print(summary_line("Campagnes ASI0x", ok, len(outcomes)))
    return 0 if ok == len(outcomes) else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("Interrompu.", file=sys.stderr)
        sys.exit(130)
