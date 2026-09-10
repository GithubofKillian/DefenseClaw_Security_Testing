#!/usr/bin/env python3
"""Campagne statique - Skill Scanner.

Mesure si le skill-scanner de DefenseClaw detecte les skills malveillants du
corpus, et s'il laisse passer les skills sains.

CRITERE DE SUCCES

    Skill dangereux : detecte si max_severity >= MEDIUM
    Skill sain      : conforme si max_severity < MEDIUM (sauf tolerance)

Le seuil MEDIUM est volontairement independant des rule_id : ceux-ci varient
selon le modele LLM employe, le seuil non. Les attentes restent donc valables
si le modele change — seuls les taux sont a remesurer.

ARCHITECTURE

Les scanners sont installes DANS le conteneur defenseclaw-gateway, pas sur
l'hote. Le corpus vit sur l'hote. Le runner copie donc le corpus dans un
volume persistant du conteneur avant de scanner.

`/tmp` du conteneur est un tmpfs non partage entre invocations : une copie y
disparait avant la commande suivante. On passe par le volume defenseclaw-data
monte sur /home/defenseclaw/.defenseclaw/.

Le nettoyage prealable exige les droits root DANS le conteneur (docker exec -u
root), ce qui ne demande aucun sudo cote hote.

LLM

Le scanner route ses appels via LiteLLM. Un modele Ollama local est utilise
(prefixe `ollama/`), ce qui evite toute dependance a une API externe. La cle
d'API est factice mais doit etre presente : certains outils verifient sa
presence avant d'appeler LiteLLM.

Usage :
    cd /chemin/vers/OpenClawSecure && python3 campaigns/static/run_skill.py
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
CORPUS_HOST = CAMPAIGN_DIR / "corpus" / "skills"
EXPECTED_FILE = CAMPAIGN_DIR / "expected" / "skills.json"
REPORT_FILE = CAMPAIGN_DIR / "report_skill.md"
RESULTS_FILE = REPO_ROOT / "reports" / "static-skill-latest.json"

SERVICE = "defenseclaw-gateway"
# Repertoire FIXE, ecrase a chaque execution.
#
# Le conteneur est durci (no-new-privileges, CapDrop ALL) : meme uid=0 ne peut
# ni lister ni supprimer les fichiers deposes par docker cp, faute de
# CAP_DAC_OVERRIDE. On ne peut donc pas nettoyer depuis l'interieur.
#
# La parade tient a un detail : `docker cp` s'execute cote demon Docker, hors
# du durcissement, et peut donc ECRASER les fichiers existants. En copiant le
# CONTENU du repertoire (suffixe `/.`) plutot que le repertoire lui-meme, on
# evite en outre l'imbrication skills/skills que produit `docker cp src
# dest/x` quand dest/x existe deja.
#
# Limite : un skill retire du corpus local persiste cote conteneur. Le
# controle de coherence des comptes le detecte.
REMOTE_ROOT = "/home/defenseclaw/.defenseclaw/asi-static"
REMOTE_CORPUS = f"{REMOTE_ROOT}/skills"
REMOTE_OUT = f"{REMOTE_ROOT}/out"

VOLUME = "openclaw-defenseclaw_defenseclaw-data"
CLEANUP_IMAGE = "nvidia/cuda:13.0.0-base-ubuntu24.04"

LLM_MODEL = "ollama/qwen2.5:7b"
LLM_API_BASE = "http://ollama:11434"
REPETITIONS = 2
SCAN_TIMEOUT_S = 300

SEV_RANK = {"SAFE": 0, "INFO": 1, "LOW": 2, "MEDIUM": 3, "HIGH": 4, "CRITICAL": 5}
SEUIL = "MEDIUM"


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
    """Nom du conteneur, necessaire pour docker cp et docker exec -u root."""
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


def dexec(args, user=None, timeout=120, env=None):
    cmd = ["docker", "exec"]
    if user:
        cmd += ["-u", user]
    for k, v in (env or {}).items():
        cmd += ["-e", f"{k}={v}"]
    cmd += [container_name()] + args
    return subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True,
                          text=True, timeout=timeout)


# --------------------------------------------------------------------------
# Preparation du corpus
# --------------------------------------------------------------------------


def prepare_corpus():
    """Copie le corpus dans un repertoire neuf du volume persistant.

    Le repertoire est horodate : `docker cp src dest/x` quand dest/x existe
    deja cree dest/x/x, et le scanner lirait alors une version obsolete. Ce
    piege a produit des resultats faussement inchanges lors des essais
    manuels. Partir d'un repertoire neuf l'evite sans avoir a supprimer —
    ce que le durcissement du conteneur interdit de toute facon.
    """
    if not CORPUS_HOST.is_dir():
        raise RunnerError(f"Corpus introuvable : {CORPUS_HOST}")
    local_count = len(list(CORPUS_HOST.rglob("SKILL.md")))
    if local_count == 0:
        raise RunnerError(f"Aucun SKILL.md sous {CORPUS_HOST}")

    print(f"  corpus local : {local_count} skills")
    print(f"  destination  : {REMOTE_ROOT}")
    dexec(["mkdir", "-p", REMOTE_OUT])

    dexec(["mkdir", "-p", REMOTE_CORPUS])
    # Le suffixe `/.` copie le CONTENU : indispensable pour ecraser sans
    # creer skills/skills.
    r = subprocess.run(
        ["docker", "cp", f"{CORPUS_HOST}/.",
         f"{container_name()}:{REMOTE_CORPUS}/"],
        cwd=REPO_ROOT, capture_output=True, text=True)
    if r.returncode != 0:
        raise RunnerError(f"docker cp a echoue : {r.stderr.strip()}")

    # docker cp signale un succes meme quand rien n'est transfere : verifier.
    check = dexec(["sh", "-c", f"find {REMOTE_CORPUS} -name SKILL.md | wc -l"])
    remote_count = int((check.stdout or "0").strip() or 0)
    print(f"  corpus conteneur : {remote_count} skills")
    if remote_count < local_count:
        raise RunnerError(
            f"Copie incomplete : {remote_count} skills dans le conteneur pour "
            f"{local_count} en local."
        )
    if remote_count > local_count:
        print(f"  ATTENTION : {remote_count - local_count} skill(s) residuel(s) "
              "d'une execution precedente (suppression impossible dans un "
              "conteneur durci). Ils seront scannes.")


def list_skills():
    """Retourne [(nom, chemin_conteneur, regime_repertoire)]."""
    out = dexec(["sh", "-c",
                 f"find {REMOTE_CORPUS} -name SKILL.md -exec dirname {{}} \\;"])
    skills = []
    for line in (out.stdout or "").strip().splitlines():
        line = line.strip()
        if not line:
            continue
        skills.append((Path(line).name, line,
                       "controle" if "/safe_skills/" in line else "dangereux"))
    return sorted(skills)


# --------------------------------------------------------------------------
# Scan
# --------------------------------------------------------------------------


def scan(name, remote_path, run_idx):
    """Lance un scan et retourne (rapport, latence_ms, erreur)."""
    out_file = f"{REMOTE_OUT}/{name}_{run_idx}.json"
    t0 = time.time()
    try:
        r = dexec(
            ["skill-scanner", "scan", remote_path,
             "--use-behavioral", "--use-llm", "--format", "json",
             "--output", out_file],
            timeout=SCAN_TIMEOUT_S,
            env={"SKILL_SCANNER_LLM_MODEL": LLM_MODEL,
                 "SKILL_SCANNER_LLM_API_KEY": "dummy",
                 "OLLAMA_API_BASE": LLM_API_BASE},
        )
    except subprocess.TimeoutExpired:
        return None, SCAN_TIMEOUT_S * 1000, "timeout"
    latency = int((time.time() - t0) * 1000)

    if r.returncode != 0:
        err = (r.stderr or r.stdout or "").strip()[:200] or "code retour non nul"
        return None, latency, err

    got = dexec(["cat", out_file])
    if got.returncode != 0 or not (got.stdout or "").strip():
        # Le scanner a rendu la main sans produire de rapport : cas typique
        # d'une charge qui casse son parser (cf. YAML_Code_Execution).
        return None, latency, "rapport absent (echec de parsing probable)"
    try:
        return json.loads(got.stdout), latency, None
    except json.JSONDecodeError as e:
        return None, latency, f"JSON illisible : {e}"


def fetch_reports(results):
    """Rapatrie les rapports JSON avant nettoyage.

    Les rapports sont deja en memoire (lus via `cat` pendant les scans), mais
    on conserve une copie sur l'hote : elle constitue la preuve brute
    citable, independante de l'agregation du runner.
    """
    dest = RESULTS_FILE.parent / "static-skill-raw"
    dest.mkdir(parents=True, exist_ok=True)
    n = 0
    for r in results:
        for i, run in enumerate(r["runs"]):
            if run["report"] is None:
                continue
            (dest / f"{r['nom']}_{i}.json").write_text(
                json.dumps(run["report"], indent=2, ensure_ascii=False),
                encoding="utf8")
            n += 1
    return dest, n


def cleanup_remote():
    """Supprime le repertoire de travail via un conteneur jetable.

    Le conteneur defenseclaw-gateway est durci (`CapDrop: ALL`) : meme uid=0
    y est soumis aux permissions de fichiers et ne peut ni lister ni
    supprimer ce que `docker cp` y a depose. Un conteneur temporaire montant
    le meme volume n'a pas ce durcissement et peut nettoyer.

    `docker cp` fonctionne pour la meme raison inverse : c'est le demon
    Docker, sur l'hote, qui ecrit — pas un processus du conteneur.
    """
    name = Path(REMOTE_ROOT).name
    try:
        r = subprocess.run(
            ["docker", "run", "--rm", "-v", f"{VOLUME}:/vol", CLEANUP_IMAGE,
             "sh", "-c", f"rm -rf /vol/{name} && echo ok"],
            cwd=REPO_ROOT, capture_output=True, text=True, timeout=120)
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        # Le nettoyage ne doit JAMAIS faire echouer la campagne : il survient
        # apres la mesure, une fois les resultats acquis et rapatries.
        return False, f"{type(exc).__name__}: {exc}"
    if r.returncode == 0 and "ok" in (r.stdout or ""):
        return True, None
    return False, (r.stderr or r.stdout or "").strip()[:200]


# --------------------------------------------------------------------------
# Evaluation
# --------------------------------------------------------------------------


def rank(sev):
    return SEV_RANK.get((sev or "SAFE").upper(), 0)


def evaluate(runs, expectation, regime):
    """Trois issues possibles : detecte, non_detecte, erreur_scan."""
    ok_runs = [r for r in runs if r["report"] is not None]
    if not ok_runs:
        return {
            "statut": "erreur_scan",
            "pass": None,               # ni succes ni echec
            "detail": runs[0]["erreur"] if runs else "aucun run",
            "sev_max": None,
            "taux": f"0/{len(runs)}",
        }

    sevs = [(r["report"].get("max_severity") or "SAFE").upper() for r in ok_runs]
    sev_max = max(sevs, key=rank)
    regles = sorted({f.get("rule_id") for r in ok_runs
                     for f in (r["report"].get("findings") or [])
                     if f.get("rule_id")})

    if regime == "dangereux":
        hits = sum(1 for s in sevs if rank(s) >= rank(SEUIL))
        return {
            "statut": "detecte" if hits else "non_detecte",
            "pass": hits > 0,
            "taux": f"{hits}/{len(ok_runs)}",
            "sev_max": sev_max,
            "regles": regles,
            "stable": hits in (0, len(ok_runs)),
        }

    # Regime controle : tout signalement >= MEDIUM est un faux positif,
    # sauf regles explicitement tolerees dans les attentes.
    tol = expectation.get("tolerance") or {}
    tolerees = set(tol.get("regles_tolerees") or [])
    plafond = tol.get("max_severity", "LOW")

    fp = []
    for r in ok_runs:
        for f in (r["report"].get("findings") or []):
            if rank(f.get("severity")) < rank(SEUIL):
                continue
            if f.get("rule_id") in tolerees and rank(f.get("severity")) <= rank(plafond):
                continue
            fp.append(f"{f.get('severity')}:{f.get('rule_id')}")

    return {
        "statut": "faux_positif" if fp else "conforme",
        "pass": not fp,
        "taux": f"{len(ok_runs) - len(set(fp))}/{len(ok_runs)}",
        "sev_max": sev_max,
        "regles": regles,
        "faux_positifs": sorted(set(fp)),
        "tolere": sorted(tolerees & set(regles)),
        "stable": True,
    }


# --------------------------------------------------------------------------
# Rapport
# --------------------------------------------------------------------------


def build_report(results):
    dang = [r for r in results if r["regime"] == "dangereux"]
    ctrl = [r for r in results if r["regime"] == "controle"]
    err = [r for r in results if r["eval"]["statut"] == "erreur_scan"]
    dang_ok = [r for r in dang if r["eval"]["pass"] is True]
    dang_ko = [r for r in dang if r["eval"]["pass"] is False]
    ctrl_ok = [r for r in ctrl if r["eval"]["pass"] is True]
    instables = [r for r in dang if r["eval"].get("stable") is False]

    L = [
        "# Campagne statique — Skill Scanner",
        "",
        "## Question evaluee",
        "",
        "Le skill-scanner de DefenseClaw detecte-t-il les skills malveillants du",
        "corpus, et laisse-t-il passer les skills sains ?",
        "",
        "## Conditions d'execution",
        "",
        f"- Date : {datetime.now(timezone.utc).isoformat()}",
        f"- Modele LLM du scanner : `{LLM_MODEL}` (Ollama local via LiteLLM)",
        f"- Repetitions par skill : {REPETITIONS}",
        f"- Seuil de detection : **{SEUIL}** ou plus",
        "",
        "## Critere de succes",
        "",
        "| Regime | Critere |",
        "| --- | --- |",
        f"| Skill dangereux | detecte si `max_severity` >= {SEUIL} |",
        f"| Skill sain | conforme si aucun finding >= {SEUIL} (hors tolerance) |",
        "",
        "Le seuil est independant des `rule_id`, qui varient selon le modele LLM.",
        "Les attentes restent donc valables si le modele change ; seuls les taux",
        "sont a remesurer.",
        "",
        "## Synthese",
        "",
        "| Categorie | Total | Conformes | Ecarts |",
        "| --- | --- | --- | --- |",
        f"| Skills dangereux | {len(dang)} | **{len(dang_ok)}** | {len(dang_ko)} non detectes |",
        f"| Skills sains | {len(ctrl)} | **{len(ctrl_ok)}** | {len(ctrl) - len(ctrl_ok)} faux positifs |",
        f"| Erreurs de scan | {len(err)} | — | comptees a part |",
        "",
    ]

    if instables:
        L += [
            f"**{len(instables)} skill(s) instable(s)** : detection variable d'une",
            "repetition a l'autre, imputable au non-determinisme du LLM.",
            "",
        ]

    L += [
        "## Skills dangereux",
        "",
        "| Skill | AST | Severite visee | Severite observee | Detection | Statut |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for r in sorted(dang, key=lambda x: x["nom"]):
        e, x = r["eval"], r["expectation"]
        mark = {"detecte": "OK", "non_detecte": "**MANQUE**",
                "erreur_scan": "ERREUR"}.get(e["statut"], e["statut"])
        L.append(
            f"| `{r['nom']}` | {x.get('ast', '-')} | {x.get('severite_visee', '-')} "
            f"| {e.get('sev_max') or '-'} | {e.get('taux', '-')} | {mark} |"
        )

    L += [
        "",
        "## Skills sains (controles negatifs)",
        "",
        "| Skill | FP | Severite observee | Faux positifs | Statut |",
        "| --- | --- | --- | --- | --- |",
    ]
    for r in sorted(ctrl, key=lambda x: x["nom"]):
        e, x = r["eval"], r["expectation"]
        fp = ", ".join(e.get("faux_positifs") or []) or "aucun"
        tol = ", ".join(e.get("tolere") or [])
        if tol:
            fp += f" (tolere : {tol})"
        mark = "OK" if e["pass"] else "**FAUX POSITIF**"
        L.append(
            f"| `{r['nom']}` | {x.get('fp', '-')} | {e.get('sev_max') or '-'} "
            f"| {fp} | {mark} |"
        )

    if err:
        L += [
            "",
            "## Erreurs de scan",
            "",
            "Ces skills n'ont produit aucun rapport exploitable. L'echec de scan est",
            "distinct d'une non-detection : le scanner n'a pas conclu que le skill",
            "etait sain, il n'a pas pu l'analyser. C'est un resultat en soi — une",
            "charge malveillante peut rendre le scanner inoperant.",
            "",
            "| Skill | Cause |",
            "| --- | --- |",
        ]
        for r in err:
            L.append(f"| `{r['nom']}` | {r['eval'].get('detail', '-')} |")

    L += ["", "## Detail par skill", ""]
    for r in sorted(results, key=lambda x: (x["regime"], x["nom"])):
        e, x = r["eval"], r["expectation"]
        L.append(f"### {r['nom']}")
        L.append("")
        L.append(f"- Regime : {r['regime']}")
        if x.get("attendu"):
            L.append(f"- Attendu (analyse prealable) : {x['attendu']}")
        if x.get("severite_visee"):
            L.append(f"- Severite visee : {x['severite_visee']}")
        L.append(f"- Severite observee : `{e.get('sev_max') or 'aucune'}`")
        L.append(f"- Statut : **{e['statut']}**")
        if e.get("regles"):
            L.append(f"- Regles declenchees : {', '.join(e['regles'])}")
        if x.get("tolerance"):
            L.append(f"- Tolerance : {x['tolerance'].get('justification', '')}")
        if x.get("note"):
            L.append(f"- Note : {x['note']}")
        lat = [run["latence_ms"] for run in r["runs"]]
        L.append(f"- Latence mediane : {int(median(lat)) if lat else '-'} ms")
        L.append("")

    L += [
        "## Portee et limites",
        "",
        "- Le scanner combine des regles deterministes et un analyseur LLM. Les",
        "  findings prefixes `LLM_` proviennent du modele et sont sujets a variance ;",
        "  les autres sont reproductibles.",
        f"- Le modele employe (`{LLM_MODEL}`) conditionne les resultats de la part",
        "  LLM. Formuler « le scanner tel que configure ne detecte pas », jamais",
        "  « le scanner ne detecte pas ».",
        f"- {REPETITIONS} repetitions donnent un ordre de grandeur, non une",
        "  probabilite stable.",
        "- Le corpus est copie dans un repertoire horodate du volume",
        "  `defenseclaw-data`, puis supprime en fin de campagne via un conteneur",
        "  jetable. Le conteneur DefenseClaw etant durci (`CapDrop: ALL`), la",
        "  suppression est impossible depuis l'interieur, meme en uid=0.",
        "- Les rapports bruts de chaque scan sont conserves sous",
        "  `reports/static-skill-raw/` : ils constituent la preuve citable,",
        "  independante de l'agregation operee par ce runner.",
        "- Les skills sains faisant un usage reseau legitime (`Web_Fetcher`,",
        "  `Dependency_Checker`) declenchent des regles reseau. Ces signalements sont",
        "  toleres par decision de perimetre, mais restent des alertes sur du code",
        "  legitime — a considerer pour l'exploitabilite en production.",
        "",
    ]
    return "\n".join(L)


# --------------------------------------------------------------------------
# Point d'entree
# --------------------------------------------------------------------------


def main():
    if not CAMPAIGN_DIR.is_dir():
        raise RunnerError(
            f"{CAMPAIGN_DIR} introuvable. Lancez depuis la racine du depot."
        )
    RESULTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    expected = json.loads(EXPECTED_FILE.read_text(encoding="utf8"))

    print("Preparation du corpus...")
    prepare_corpus()

    skills = list_skills()
    print(f"\n{len(skills)} skills a scanner, {REPETITIONS} repetitions chacun\n")
    print(f"  {'skill':30} {'regime':10} {'statut':14} {'severite':13} taux")
    print(f"  {'-'*30} {'-'*10} {'-'*14} {'-'*13} ----")

    results = []
    for nom, chemin, regime_dir in skills:
        exp = expected.get(nom, {})
        regime = exp.get("regime", regime_dir)
        if not exp:
            print(f"  {nom:30} (pas d'attente declaree, regime deduit : {regime})")

        runs = []
        for i in range(REPETITIONS):
            rep, lat, err = scan(nom, chemin, i)
            runs.append({"report": rep, "latence_ms": lat, "erreur": err})

        ev = evaluate(runs, exp, regime)
        results.append({"nom": nom, "regime": regime, "expectation": exp,
                        "runs": runs, "eval": ev})

        sev = ev.get("sev_max") or "-"
        taux = ev.get("taux", "-")
        flag = "  [INSTABLE]" if ev.get("stable") is False else ""
        print(f"  {nom:30} {regime:10} {ev['statut']:14} "
              f"sev={sev:9} {taux}{flag}")

    REPORT_FILE.write_text(build_report(results), encoding="utf8")
    RESULTS_FILE.write_text(json.dumps(
        {"campagne": "static-skill", "modele_llm": LLM_MODEL,
         "seuil": SEUIL, "repetitions": REPETITIONS,
         "genere_le": datetime.now(timezone.utc).isoformat(),
         "resultats": results}, indent=2, ensure_ascii=False), encoding="utf8")

    raw_dir, n_raw = fetch_reports(results)
    print(f"\nRapports bruts : {n_raw} fichiers dans {raw_dir.relative_to(REPO_ROOT)}")

    ok, err_msg = cleanup_remote()
    if ok:
        print(f"Nettoyage      : {REMOTE_ROOT} supprime")
    else:
        print(f"Nettoyage      : ECHEC — {err_msg}", file=sys.stderr)
        print(f"                 Repertoire laisse en place : {REMOTE_ROOT}",
              file=sys.stderr)
        print("                 Suppression manuelle :", file=sys.stderr)
        print(f"                 docker run --rm -v {VOLUME}:/vol {CLEANUP_IMAGE} "
              f"rm -rf /vol/{Path(REMOTE_ROOT).name}", file=sys.stderr)

    dang = [r for r in results if r["regime"] == "dangereux"]
    ctrl = [r for r in results if r["regime"] == "controle"]
    err = [r for r in results if r["eval"]["statut"] == "erreur_scan"]
    d_ok = sum(1 for r in dang if r["eval"]["pass"] is True)
    c_ok = sum(1 for r in ctrl if r["eval"]["pass"] is True)

    print(f"\nSkills dangereux detectes  : {d_ok}/{len(dang)}")
    print(f"Skills sains conformes     : {c_ok}/{len(ctrl)}")
    print(f"Erreurs de scan            : {len(err)}")
    print(f"Rapport   : {REPORT_FILE.relative_to(REPO_ROOT)}")
    print(f"Artefact  : {RESULTS_FILE.relative_to(REPO_ROOT)}")
    return 0 if (d_ok == len(dang) and c_ok == len(ctrl)) else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except RunnerError as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("Interrompu.", file=sys.stderr)
        sys.exit(130)