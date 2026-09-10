#!/usr/bin/env python3
"""Campagne statique - MCP Scanner.

Mesure si le mcp-scanner de DefenseClaw detecte les menaces exposees par des
serveurs MCP malveillants : injection dans les ressources, les prompts, les
descriptions d'outils, les metadonnees serveur, ou les arguments.

CRITERE DE SUCCES

    Scenario malveillant : detecte si la severite maximale >= MEDIUM

Le seuil est independant des rule_id, qui varient selon le modele LLM. Les
attentes restent donc valables si le modele change ; seuls les taux sont a
remesurer.

DEUX TRANSPORTS, DEUX TRAITEMENTS

  stdio — le scanner lance lui-meme le serveur, l'interroge et l'arrete.
          Aucun cycle de vie a piloter cote runner.

  sse   — le serveur ecoute sur un port. Le runner le demarre en arriere-plan,
          attend qu'il reponde, lance le scan par --server-url, puis l'arrete.

Les serveurs SSE ecoutent sur 127.0.0.1 (cf. server_base.py) : le scanner doit
donc tourner DANS le meme conteneur, ce qui est le cas — tout se passe dans
defenseclaw-gateway.

SOUS-COMMANDES

La surface exposee determine la sous-commande :

    resources     ressources exposees par le serveur
    prompts       gabarits de prompt
    instructions  metadonnees du serveur (champ instructions=)
    remote        outils exposes
    stdio         serveur lance par le scanner

ARCHITECTURE

Les scanners sont installes DANS le conteneur defenseclaw-gateway. Le corpus
vit sur l'hote et y est copie avant chaque campagne. Le conteneur etant durci
(CapDrop ALL), la suppression y est impossible : on ecrase par
`docker cp source/. dest/`, qui s'execute cote demon Docker.

Usage :
    cd /chemin/vers/OpenClawSecure && python3 campaigns/static/run_mcp.py
"""

import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from statistics import median

REPO_ROOT = Path.cwd()
CAMPAIGN_DIR = REPO_ROOT / "campaigns" / "static"
CORPUS_HOST = CAMPAIGN_DIR / "corpus" / "mcp"
EXPECTED_FILE = CAMPAIGN_DIR / "expected" / "mcp.json"
REPORT_FILE = CAMPAIGN_DIR / "report_mcp.md"
RESULTS_FILE = REPO_ROOT / "reports" / "static-mcp-latest.json"
RAW_DIR = REPO_ROOT / "reports" / "static-mcp-raw"

SERVICE = "defenseclaw-gateway"
REMOTE_ROOT = "/home/defenseclaw/.defenseclaw/asi-mcp"
REMOTE_CORPUS = f"{REMOTE_ROOT}/mcp"
CLEANUP_IMAGE = "nvidia/cuda:13.0.0-base-ubuntu24.04"
VOLUME = "openclaw-defenseclaw_defenseclaw-data"

LLM_MODEL = "ollama/qwen2.5:7b"
LLM_API_BASE = "http://ollama:11434"
ANALYZERS = "yara,llm"
REPETITIONS = 2
SCAN_TIMEOUT_S = 300
SERVER_BOOT_TIMEOUT_S = 20

SEV_RANK = {"SAFE": 0, "INFO": 1, "LOW": 2, "MEDIUM": 3, "HIGH": 4, "CRITICAL": 5}
SEUIL = "MEDIUM"

LLM_ENV = {
    "MCP_SCANNER_LLM_MODEL": LLM_MODEL,
    "MCP_SCANNER_LLM_API_KEY": "dummy",
    "OLLAMA_API_BASE": LLM_API_BASE,
}


class RunnerError(RuntimeError):
    """Erreur d'execution du runner."""


_COMPOSE = None
_CONTAINER = None


def compose_cmd():
    global _COMPOSE
    if _COMPOSE is not None:
        return _COMPOSE
    for cand in (["docker", "compose"], ["docker-compose"]):
        try:
            if subprocess.run(cand + ["version"], cwd=REPO_ROOT,
                              capture_output=True).returncode == 0:
                _COMPOSE = cand
                return _COMPOSE
        except FileNotFoundError:
            continue
    raise RunnerError("Ni `docker compose` ni `docker-compose` disponible.")


def container_name():
    global _CONTAINER
    if _CONTAINER is not None:
        return _CONTAINER
    r = subprocess.run(compose_cmd() + ["ps", "-q", SERVICE],
                       cwd=REPO_ROOT, capture_output=True, text=True)
    cid = (r.stdout or "").strip().splitlines()
    if not cid:
        raise RunnerError(f"Conteneur {SERVICE} introuvable. Stack demarree ?")
    _CONTAINER = cid[0]
    return _CONTAINER


def dexec(args, detach=False, timeout=120, env=None):
    cmd = ["docker", "exec"]
    if detach:
        cmd.append("-d")
    for k, v in (env or {}).items():
        cmd += ["-e", f"{k}={v}"]
    cmd += [container_name()] + args
    return subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True,
                          text=True, timeout=timeout)


# --------------------------------------------------------------------------
# Corpus
# --------------------------------------------------------------------------


def prepare_corpus():
    if not CORPUS_HOST.is_dir():
        raise RunnerError(f"Corpus introuvable : {CORPUS_HOST}")
    local = sorted(p.name for p in CORPUS_HOST.rglob("*.py"))
    if not local:
        raise RunnerError(f"Aucun .py sous {CORPUS_HOST}")

    print(f"  corpus local : {len(local)} fichiers")
    dexec(["mkdir", "-p", REMOTE_CORPUS])
    # Le suffixe `/.` copie le CONTENU : evite l'imbrication mcp/mcp que
    # produit `docker cp src dest/x` quand dest/x existe deja.
    r = subprocess.run(
        ["docker", "cp", f"{CORPUS_HOST}/.", f"{container_name()}:{REMOTE_CORPUS}/"],
        cwd=REPO_ROOT, capture_output=True, text=True)
    if r.returncode != 0:
        raise RunnerError(f"docker cp a echoue : {r.stderr.strip()}")

    chk = dexec(["sh", "-c", f"find {REMOTE_CORPUS} -name '*.py' | wc -l"])
    remote = int((chk.stdout or "0").strip() or 0)
    print(f"  corpus conteneur : {remote} fichiers")
    if remote < len(local):
        raise RunnerError(f"Copie incomplete : {remote} pour {len(local)} attendus.")


def cleanup():
    """Supprime le corpus du volume via un conteneur non durci.

    Le conteneur defenseclaw-gateway a CapDrop ALL : meme uid=0 n'y peut rien
    supprimer. Un conteneur jetable monte le volume avec ses capacites par
    defaut. L'image doit etre disponible localement — le registre Docker est
    inaccessible depuis ce reseau (interception TLS).
    """
    r = subprocess.run(
        ["docker", "run", "--rm", "-v", f"{VOLUME}:/vol", CLEANUP_IMAGE,
         "sh", "-c", f"rm -rf /vol/{Path(REMOTE_ROOT).name}"],
        cwd=REPO_ROOT, capture_output=True, text=True)
    if r.returncode == 0:
        print(f"Nettoyage      : {REMOTE_ROOT} supprime")
    else:
        print(f"Nettoyage      : ECHEC — {(r.stderr or '').strip()[:120]}")
        print(f"                 Suppression manuelle :")
        print(f"                 docker run --rm -v {VOLUME}:/vol "
              f"{CLEANUP_IMAGE} rm -rf /vol/{Path(REMOTE_ROOT).name}")


# --------------------------------------------------------------------------
# Cycle de vie des serveurs SSE
# --------------------------------------------------------------------------


def start_server(fichier, port):
    """Demarre un serveur SSE en arriere-plan et attend qu'il reponde."""
    chemin = f"{REMOTE_CORPUS}/{fichier}"
    workdir = str(Path(chemin).parent)
    # PYTHONPATH pointe sur dynamic_scenarios : les serveurs importent
    # server_base depuis ce repertoire.
    base = f"{REMOTE_CORPUS}/dynamic_scenarios"
    dexec(["sh", "-c",
           f"cd {workdir} && PYTHONPATH={base} nohup python3 {chemin} "
           f"> /tmp/mcp_{port}.log 2>&1 &"], detach=True)

    deadline = time.time() + SERVER_BOOT_TIMEOUT_S
    while time.time() < deadline:
        time.sleep(1)
        probe = dexec(["sh", "-c",
                       f"python3 -c \"import socket;s=socket.socket();"
                       f"s.settimeout(1);s.connect(('127.0.0.1',{port}));"
                       f"print('up')\" 2>/dev/null"])
        if "up" in (probe.stdout or ""):
            return True, None
    log = dexec(["sh", "-c", f"tail -5 /tmp/mcp_{port}.log 2>/dev/null"])
    return False, (log.stdout or "").strip()[:200] or "port jamais ouvert"


def stop_server(fichier):
    """Arrete le serveur. docker exec -d ne rend pas de PID exploitable."""
    dexec(["pkill", "-f", Path(fichier).name])
    time.sleep(1)


# --------------------------------------------------------------------------
# Scan
# --------------------------------------------------------------------------


def scan_stdio(sc, run_idx):
    chemin = f"{REMOTE_CORPUS}/{sc['fichier']}"
    # --analyzers et --format sont des options GLOBALES : elles doivent
    # preceder la sous-commande, sinon argparse les rejette.
    args = ["mcp-scanner", "--analyzers", ANALYZERS, "--format", "raw",
            "stdio", "--stdio-command", "python3", f"--stdio-arg={chemin}"]
    return _run_scan(args, run_idx)


def scan_sse(sc, run_idx):
    url = f"http://127.0.0.1:{sc['port']}/sse"
    args = ["mcp-scanner", "--analyzers", ANALYZERS, "--format", "raw",
            sc["sous_commande"], "--server-url", url]
    return _run_scan(args, run_idx)


def _run_scan(args, run_idx):
    t0 = time.time()
    try:
        r = dexec(args, timeout=SCAN_TIMEOUT_S, env=LLM_ENV)
    except subprocess.TimeoutExpired:
        return None, SCAN_TIMEOUT_S * 1000, "timeout"
    lat = int((time.time() - t0) * 1000)
    out = (r.stdout or "").strip()
    if not out:
        err = (r.stderr or "").strip()[:200] or "sortie vide"
        return None, lat, err
    # --format raw ecrit le JSON sur stdout ; il peut etre precede de logs.
    start = out.find("{")
    if start == -1:
        return None, lat, f"pas de JSON en sortie : {out[:150]}"
    try:
        return json.loads(out[start:]), lat, None
    except json.JSONDecodeError as e:
        return None, lat, f"JSON illisible : {e}"


# --------------------------------------------------------------------------
# Evaluation
# --------------------------------------------------------------------------


def rank(sev):
    return SEV_RANK.get((sev or "SAFE").upper(), 0)


def extract(report):
    """Extrait (severite_max, regles) d'un rapport, quelle que soit sa forme.

    Le format `raw` varie selon la sous-commande : les findings peuvent etre
    a la racine, sous `results`, ou groupes par outil. On parcourt donc la
    structure a la recherche des cles connues.
    """
    sevs, rules = [], set()

    def walk(node):
        if isinstance(node, dict):
            sev = node.get("severity")
            if isinstance(sev, str):
                sevs.append(sev.upper())
            for k in ("rule_id", "rule", "analyzer", "name"):
                v = node.get(k)
                if isinstance(v, str) and node.get("severity"):
                    rules.add(v)
                    break
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(report)
    sev_max = max(sevs, key=rank) if sevs else "SAFE"
    return sev_max, sorted(rules)


def evaluate(runs):
    ok = [r for r in runs if r["report"] is not None]
    if not ok:
        return {"statut": "erreur_scan", "pass": None,
                "detail": runs[0]["erreur"] if runs else "aucun run",
                "sev_max": None, "taux": f"0/{len(runs)}", "regles": []}

    infos = [extract(r["report"]) for r in ok]
    sevs = [i[0] for i in infos]
    rules = sorted({x for i in infos for x in i[1]})
    sev_max = max(sevs, key=rank)
    hits = sum(1 for s in sevs if rank(s) >= rank(SEUIL))
    return {
        "statut": "detecte" if hits else "non_detecte",
        "pass": hits > 0,
        "taux": f"{hits}/{len(ok)}",
        "sev_max": sev_max,
        "regles": rules,
        "stable": hits in (0, len(ok)),
    }


# --------------------------------------------------------------------------
# Rapport
# --------------------------------------------------------------------------


def build_report(results):
    det = [r for r in results if r["eval"]["pass"] is True]
    non = [r for r in results if r["eval"]["pass"] is False]
    err = [r for r in results if r["eval"]["statut"] == "erreur_scan"]
    inst = [r for r in results if r["eval"].get("stable") is False]

    L = [
        "# Campagne statique — MCP Scanner",
        "",
        "## Question evaluee",
        "",
        "Le mcp-scanner de DefenseClaw detecte-t-il les menaces exposees par un",
        "serveur MCP malveillant : injection dans les ressources, les prompts, les",
        "descriptions d'outils, les metadonnees serveur ou les arguments ?",
        "",
        "## Conditions d'execution",
        "",
        f"- Date : {datetime.now(timezone.utc).isoformat()}",
        f"- Analyseurs : `{ANALYZERS}`",
        f"- Modele LLM : `{LLM_MODEL}` (Ollama local via LiteLLM)",
        f"- Repetitions : {REPETITIONS}",
        f"- Seuil de detection : **{SEUIL}** ou plus",
        "",
        "## Deux transports",
        "",
        "| Transport | Fonctionnement | Scenarios |",
        "| --- | --- | --- |",
        "| `stdio` | le scanner lance le serveur, l'interroge, l'arrete | 4 |",
        "| `sse` | le runner demarre le serveur sur un port, le scanner l'interroge par URL | 5 |",
        "",
        "Les serveurs SSE ecoutent sur `127.0.0.1` : le scanner tourne donc dans le",
        "meme conteneur.",
        "",
        "## Synthese",
        "",
        "| Indicateur | Valeur |",
        "| --- | --- |",
        f"| Scenarios malveillants | {len(results)} |",
        f"| **Detectes** | **{len(det)}** |",
        f"| Non detectes | {len(non)} |",
        f"| Erreurs de scan | {len(err)} |",
        f"| Instables | {len(inst)} |",
        "",
        "## Resultats",
        "",
        "| Scenario | MCP | Surface | Transport | Severite visee | Observee | Taux | Statut |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for r in sorted(results, key=lambda x: x["nom"]):
        e, x = r["eval"], r["expectation"]
        mark = {"detecte": "OK", "non_detecte": "**MANQUE**",
                "erreur_scan": "ERREUR"}.get(e["statut"], e["statut"])
        L.append(
            f"| `{r['nom']}` | {x.get('mcp', '-')} | {x.get('surface', '-')} "
            f"| {x.get('transport', '-')} | {x.get('severite_visee', '-')} "
            f"| {e.get('sev_max') or '-'} | {e.get('taux', '-')} | {mark} |"
        )

    L += ["", "## Detail par scenario", ""]
    for r in sorted(results, key=lambda x: x["nom"]):
        e, x = r["eval"], r["expectation"]
        L.append(f"### {r['nom']}")
        L.append("")
        L.append(f"- Reference MCP : {x.get('mcp', '-')}")
        L.append(f"- Surface visee : {x.get('surface', '-')}")
        L.append(f"- Transport : {x.get('transport', '-')}"
                 + (f" (port {x['port']}, sous-commande `{x['sous_commande']}`)"
                    if x.get("transport") == "sse" else ""))
        L.append(f"- Attendu (analyse prealable) : {x.get('attendu', '-')}")
        L.append(f"- Severite visee : {x.get('severite_visee', '-')}")
        L.append(f"- Severite observee : `{e.get('sev_max') or 'aucune'}`")
        L.append(f"- Statut : **{e['statut']}** ({e.get('taux', '-')})")
        if e.get("regles"):
            L.append(f"- Regles declenchees : {', '.join(e['regles'][:10])}")
        if x.get("controle_negatif"):
            L.append(f"- Controle negatif expose : {x['controle_negatif']}")
        if e.get("detail"):
            L.append(f"- Cause de l'echec : {e['detail']}")
        lat = [run["latence_ms"] for run in r["runs"]]
        L.append(f"- Latence mediane : {int(median(lat)) if lat else '-'} ms")
        L.append("")

    L += [
        "## Portee et limites",
        "",
        "- Chaque scenario est scanne ISOLEMENT, un serveur par scenario. Un serveur",
        "  unique regroupant toutes les charges rendrait l'attribution des findings",
        "  impossible et priverait les controles negatifs de leur sens.",
        "- Plusieurs serveurs exposent une ressource ou un outil SAIN a cote de la",
        "  charge (colonne « controle negatif expose »). Le scanner ne les distingue",
        "  pas dans son verdict global : leur presence sert a verifier que la",
        "  detection ne se declenche pas sur tout le serveur indistinctement.",
        f"- Le modele employe (`{LLM_MODEL}`) conditionne la part LLM des resultats.",
        "  Formuler « le scanner tel que configure ne detecte pas », jamais",
        "  « le scanner ne detecte pas ».",
        f"- {REPETITIONS} repetitions donnent un ordre de grandeur, non une",
        "  probabilite stable.",
        "- La campagne mesure l'analyse d'un serveur MCP, pas le comportement d'un",
        "  agent qui le consommerait reellement.",
        "",
    ]
    return "\n".join(L)


# --------------------------------------------------------------------------
# Point d'entree
# --------------------------------------------------------------------------


def main():
    if not CAMPAIGN_DIR.is_dir():
        raise RunnerError(f"{CAMPAIGN_DIR} introuvable. Lancez depuis la racine.")
    RESULTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    expected = json.loads(EXPECTED_FILE.read_text(encoding="utf8"))
    scenarios = {k: v for k, v in expected.items() if not k.startswith("_")}

    print("Preparation du corpus...")
    prepare_corpus()

    print(f"\n{len(scenarios)} scenarios, {REPETITIONS} repetitions chacun\n")
    print(f"  {'scenario':30} {'transport':10} {'statut':14} {'severite':13} taux")
    print(f"  {'-'*30} {'-'*10} {'-'*14} {'-'*13} ----")

    results = []
    try:
        for nom, sc in sorted(scenarios.items()):
            runs = []
            for i in range(REPETITIONS):
                if sc["transport"] == "stdio":
                    rep, lat, err = scan_stdio(sc, i)
                else:
                    up, boot_err = start_server(sc["fichier"], sc["port"])
                    if not up:
                        rep, lat, err = None, 0, f"serveur non demarre : {boot_err}"
                    else:
                        rep, lat, err = scan_sse(sc, i)
                    stop_server(sc["fichier"])
                runs.append({"report": rep, "latence_ms": lat, "erreur": err})
                if rep is not None:
                    (RAW_DIR / f"{nom}_{i}.json").write_text(
                        json.dumps(rep, indent=2, ensure_ascii=False), encoding="utf8")

            ev = evaluate(runs)
            results.append({"nom": nom, "expectation": sc, "runs": runs, "eval": ev})
            flag = "  [INSTABLE]" if ev.get("stable") is False else ""
            print(f"  {nom:30} {sc['transport']:10} {ev['statut']:14} "
                  f"sev={ev.get('sev_max') or '-':9} {ev.get('taux','-')}{flag}")
    finally:
        # Les serveurs SSE sont arretes au fil de l'eau, mais un scan interrompu
        # pourrait en laisser un actif.
        for sc in scenarios.values():
            if sc["transport"] == "sse":
                stop_server(sc["fichier"])

    REPORT_FILE.write_text(build_report(results), encoding="utf8")
    RESULTS_FILE.write_text(json.dumps(
        {"campagne": "static-mcp", "modele_llm": LLM_MODEL, "analyseurs": ANALYZERS,
         "seuil": SEUIL, "repetitions": REPETITIONS,
         "genere_le": datetime.now(timezone.utc).isoformat(),
         "resultats": results}, indent=2, ensure_ascii=False), encoding="utf8")

    det = sum(1 for r in results if r["eval"]["pass"] is True)
    err = sum(1 for r in results if r["eval"]["statut"] == "erreur_scan")

    print(f"\nRapports bruts : {len(list(RAW_DIR.glob('*.json')))} fichiers dans "
          f"{RAW_DIR.relative_to(REPO_ROOT)}")
    if err == len(results):
        # Tout a echoue : conserver le corpus pour permettre le diagnostic.
        print(f"Nettoyage      : IGNORE — corpus conserve dans {REMOTE_ROOT}")
        print("                 (tous les scans ont echoue, diagnostic possible)")
    else:
        cleanup()
    print(f"Scenarios detectes : {det}/{len(results)}")
    print(f"Erreurs de scan    : {err}")
    print(f"Rapport   : {REPORT_FILE.relative_to(REPO_ROOT)}")
    print(f"Artefact  : {RESULTS_FILE.relative_to(REPO_ROOT)}")
    return 0 if det == len(results) else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except RunnerError as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("Interrompu.", file=sys.stderr)
        sys.exit(130)