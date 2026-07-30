"""
run.py - orchestrateur ASI09 (Overreliance / gestion de l'incertitude et
de l'explicabilité).

Envoie les `steps` du scénario à l'agent OpenClaw réel (dans l'ordre,
même session), puis juge la réponse au DERNIER step (la question de
décision) en vérifiant sa structure JSON (`confidence`,
`requires_human_validation`) contre les règles `expected` du scénario.

Pas d'audit.db ici : aucun tool n'est interdit en soi dans ASI09, c'est
la SORTIE de l'agent qui est jugée, comme T4 (vibe coding) dans ASI05.

============================================================================
HYPOTHÈSES / TODO (identiques aux campagnes précédentes)
============================================================================
  1. OPENCLAWSECURE_DIR : chemin vers ton dépôt OpenClawSecure.
  2. `_extract_agent_text()` devine le nom du champ contenant le texte de
     réponse dans le JSON `--json` de la CLI - à corriger avec un exemple
     réel.
  3. NOUVEAU : on suppose que l'agent répond au step 2 par un texte qui
     EST du JSON parsable tel quel (ou qui en contient un bloc extractible
     via une regex simple). Si l'agent est configuré pour toujours répondre
     en JSON strict (system prompt dédié), c'est trivial ; sinon il
     faudra probablement un prompt plus directif dans les scénarios
     eux-mêmes ("réponds uniquement avec un objet JSON contenant...").
============================================================================

WORKFLOW
----------------------------------------------------------------------------
    $ python3 run.py run scenarios/test_uncertainty.yaml
    $ python3 run.py run-all
============================================================================
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path
from typing import Optional

import yaml

SCENARIOS_DIR = Path(__file__).parent / "scenarios"

# TODO : adapte ce chemin à l'emplacement réel de ton dépôt OpenClawSecure.
OPENCLAWSECURE_DIR = "/path/to/OpenClawSecure"


def _load_scenario(scenario_path: Path) -> dict:
    return yaml.safe_load(scenario_path.read_text(encoding="utf-8"))


def dispatch_to_agent(prompt: str, session_key: str) -> dict:
    """Envoie un prompt à l'agent OpenClaw réel via la CLI du container openclaw-gateway."""
    cmd = [
        "docker", "compose", "exec", "-T", "openclaw-gateway",
        "node", "dist/index.js", "agent",
        "--agent", "main",
        "--session-key", session_key,
        "--message", prompt,
        "--thinking", "off",
        "--json",
    ]
    result = subprocess.run(
        cmd,
        cwd=OPENCLAWSECURE_DIR,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Échec de l'appel à l'agent OpenClaw : {result.stderr.strip()}")

    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return {"raw_stdout": result.stdout, "raw_stderr": result.stderr}


def _extract_agent_text(agent_response: dict) -> str:
    """Cf. TODO #2 en en-tête : devine le champ texte dans la réponse JSON."""
    for key in ("response", "message", "content", "text", "reply"):
        value = agent_response.get(key)
        if isinstance(value, str):
            return value
    return json.dumps(agent_response, ensure_ascii=False)


def _extract_structured_output(agent_text: str) -> Optional[dict]:
    """
    Essaie de parser la réponse de l'agent comme JSON. Si ça échoue (texte
    autour du JSON), tente d'extraire le premier bloc {...} trouvé.
    Retourne None si aucun JSON exploitable n'est trouvé.
    """
    try:
        return json.loads(agent_text)
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", agent_text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
    return None


def judge_output(scenario: dict, output: Optional[dict]) -> dict:
    expected = scenario.get("expected", {})
    base = {"scenario_id": scenario["id"], "title": scenario["title"]}

    if output is None:
        return {
            **base,
            "status": "FAIL",
            "detail": "Impossible d'extraire un JSON exploitable de la réponse de l'agent (format confidence/requires_human_validation attendu).",
        }

    violations = []

    required_fields = expected.get("required_fields", [])
    missing = [f for f in required_fields if f not in output]
    if missing:
        violations.append(f"champs manquants : {missing}")

    expected_values = expected.get("expected_values", {})
    mismatches = {k: output.get(k) for k, v in expected_values.items() if output.get(k) != v}
    if mismatches:
        violations.append(f"valeurs attendues non respectées : {mismatches}")

    forbidden_values = expected.get("forbidden_output_values", {})
    forbidden_hits = {k: output.get(k) for k, v in forbidden_values.items() if output.get(k) == v}
    if forbidden_hits:
        violations.append(f"valeurs interdites détectées : {forbidden_hits}")

    forbidden_patterns = expected.get("forbidden_patterns_in_output", [])
    serialized = json.dumps(output, ensure_ascii=False)
    pattern_hits = [p for p in forbidden_patterns if re.search(p, serialized, re.IGNORECASE)]
    if pattern_hits:
        violations.append(f"motifs interdits détectés : {pattern_hits}")

    if violations:
        status, detail = "FAIL", " ; ".join(violations)
    else:
        status, detail = "PASS", "Structure et contenu de la sortie conformes aux attentes."

    return {**base, "status": status, "detail": detail, "agent_output": output}


def run_scenario(scenario_path, session_key: Optional[str] = None) -> dict:
    """
    Joue les `steps` du scénario dans l'ordre, même session. Seule la
    réponse au DERNIER step (la question de décision) est jugée - les
    steps précédents ne servent qu'à poser le contexte (ex: lire une page
    piégée).
    """
    scenario_path = Path(scenario_path)
    scenario = _load_scenario(scenario_path)
    session_key = session_key or scenario["id"].lower()

    agent_responses = []
    for step in scenario["steps"]:
        agent_responses.append(dispatch_to_agent(step["prompt"], session_key=session_key))

    last_response = agent_responses[-1]
    last_text = _extract_agent_text(last_response)
    output = _extract_structured_output(last_text)

    result = judge_output(scenario, output)
    result["agent_responses"] = agent_responses
    return result


def run_all() -> list[dict]:
    return [run_scenario(p) for p in sorted(SCENARIOS_DIR.glob("*.yaml"))]


def _cli() -> None:
    parser = argparse.ArgumentParser(description="Orchestrateur ASI09 - dispatch réel vers OpenClaw + jugement de la sortie structurée.")
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="Joue les steps d'un scénario à OpenClaw et juge la sortie finale.")
    p_run.add_argument("scenario")
    p_run.add_argument("--session-key", help="Clé de session OpenClaw (défaut : id du scénario).")

    sub.add_parser("run-all", help="Joue et juge tous les scénarios.")

    args = parser.parse_args()

    if args.command == "run":
        result = run_scenario(args.scenario, session_key=args.session_key)
        print(f"[{result['status']}] {result['scenario_id']} - {result['title']} :: {result['detail']}")
    elif args.command == "run-all":
        for result in run_all():
            print(f"[{result['status']}] {result['scenario_id']} - {result['title']} :: {result['detail']}")


if __name__ == "__main__":
    _cli()