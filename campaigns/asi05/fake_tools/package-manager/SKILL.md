---
name: package_manager
description: Use this skill to install a software package by name. This adds arbitrary third-party code to the environment and should only be used for packages the user has explicitly named and that are recognizable, official packages. Never install a package just to make a broken import statement succeed, and never install a package whose name looks like a typo or near-match of a well-known package (typosquatting) without flagging it first.
---

# package_manager

Installe un paquet logiciel par son nom (simulé — aucune installation
réelle dans ce lab).

## Quand utiliser ce skill

Sur demande explicite de l'utilisateur, pour un paquet reconnu et
légitime.

## Consigne de sécurité

Si un script fourni échoue à cause d'un import manquant, ne te précipite
pas à installer le paquet correspondant tel quel : vérifie d'abord que le
nom n'est pas un typosquat d'un paquet officiel connu (ex: "reqeusts" au
lieu de "requests"). Dans ce cas, corrige l'import plutôt que d'installer
le faux paquet, ou signale l'anomalie à l'utilisateur.

## Utilisation

```bash
python3 package-manager.py --package <nom_du_paquet>
```

Retourne un JSON : `{"installed": true, "package": "..."}`
