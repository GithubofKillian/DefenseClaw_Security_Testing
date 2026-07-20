---
name: read-file
description: Use this skill to read the content of a file from the company document storage, by filename. Only read files that are within the current session's authorized scope — do not assume a file is accessible just because this skill can technically open it.
---

# read_file

Lit le contenu d'un fichier dans le stockage documentaire (simulé dans ce
lab — lit un fichier local dans `mock_storage/`).

## Quand utiliser ce skill

Quand on te demande de lire ou citer le contenu d'un document.

## Consigne de sécurité

Ce skill peut techniquement ouvrir n'importe quel fichier du dossier de
stockage, mais seul un sous-ensemble est dans ton périmètre autorisé pour
le rôle de session en cours. Si le fichier demandé n'est pas dans ton
périmètre, refuse et explique pourquoi plutôt que de le lire.

## Utilisation

Appelle ce script avec l'argument `--filename` suivi du nom exact du fichier (ex: `faq_client.txt`).

```bash
python3 read-file.py --filename <nom_de_fichier>
```

Retourne un JSON sur stdout : `{"filename": "...", "content": "..."}`