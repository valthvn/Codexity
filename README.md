# Codexity

Un skill pour faire travailler **Codex et Antigravity** dans une même conversation Codex, avec une review indépendante et un état reprenable.

Codex reste le coordinateur et le développeur. Le runner appelle Antigravity CLI pour challenger le plan, vérifier les changements et, pour les tâches critiques, effectuer une review aveugle dans une nouvelle conversation. Le modèle et le niveau de raisonnement choisis dans Codex restent inchangés.

## Fonctionnement

| Mode | Usage |
| --- | --- |
| `auto` | Adapter le workflow au risque ; Codex seul pour les petites tâches |
| `plan` | Faire challenger un plan avant de coder |
| `review` | Vérifier les changements existants, avec une base Git et un périmètre précis |
| `loop` | Enchaîner plan, review, implémentation, tests et inspection indépendante |
| `investigate` | Faire examiner une question à partir du code, sans intégrer de modifications |
| `status` / `resume` | Consulter l’état ou reprendre après une interruption |
| `cancel` / `doctor` | Arrêter une exécution ou diagnostiquer l’installation |

La boucle conserve les plans, rapports, findings et résultats de tests. Les approbations sont liées aux empreintes SHA-256 des éléments examinés : modifier le code après une validation rend celle-ci périmée. Les rounds et les corrections sont limités ; une panne du reviewer produit un statut incomplet, jamais une approbation.

## Prérequis

- Python **3.10 ou supérieur** et Git.
- Codex avec accès au terminal du projet et aux skills locaux.
- Antigravity CLI `agy`, installé et connecté sur la même machine que les commandes du runner.
- Le modèle Antigravity configuré doit être disponible dans `agy models`.

Par défaut, le reviewer utilise `gemini-3.8-flash-high` avec un effort `high`. Le runner utilise les identifiants de connexion déjà enregistrés par la CLI, sans demander de clé API. Les appels consomment le quota du compte Antigravity.

## Installation

### Windows / PowerShell

```powershell
git clone https://github.com/valthvn/Codexity.git
py -3 .\codexity\codexity\scripts\install.py --skills-dir "$env:USERPROFILE\.codex\skills"
```

### Linux / macOS

```bash
git clone https://github.com/valthvn/Codexity.git
python3 ./codexity/codexity/scripts/install.py --skills-dir "$HOME/.codex/skills"
```

Pour une installation limitée à un projet, passer son dossier `.agents/skills` à `--skills-dir`. L’installateur refuse d’écraser une installation existante. Ouvrir ensuite une nouvelle conversation Codex.

> Si `agy` est un wrapper Windows `.cmd` ou `.bat`, configurer l’exécutable Node et le véritable point d’entrée de la CLI. Voir [la configuration Antigravity](codexity/references/antigravity.md). L’exécution native Windows reste à vérifier sur la machine cible.

## Utilisation depuis Codex

Écrire directement dans la conversation :

```text
$codexity loop Ajoute cette fonctionnalité en respectant les contraintes du projet.
```

```text
$codexity review Vérifie les changements que nous venons de faire.
```

```text
$codexity plan Challenge ce plan avant l’implémentation.
```

```text
$codexity resume
```

Codex doit conserver le chemin de l’exécution pour `resume`, `status` et `cancel`. Le skill pilote le workflow de l’agent hôte ; le script Python ne remplace pas Codex et n’implémente pas lui-même les fonctionnalités.

## Isolation et limites

Le reviewer reçoit une copie filtrée du projet, sans métadonnées Git partagées ni fichiers de secrets courants. Ses modifications éventuelles sont ignorées et dégradent la validité du rapport. Les liens symboliques ne sont pas suivis ; les instructions présentes dans les fichiers sont traitées comme des données non fiables.

Cette séparation **n’est pas une garantie de lecture seule au niveau du système d’exploitation**. Les permissions et le sandbox de la CLI restent déterminants. Le filtrage par nom ne détecte pas tous les secrets codés en dur : vérifier le contenu sensible avant de l’envoyer au reviewer.

Un `PASS` concerne le périmètre et les éléments réellement vérifiés, pas l’absence de bugs dans tout le projet. La CLI simulée des tests ne doit jamais servir à approuver un vrai changement.

## Vérification

```bash
python3 -m unittest discover -s codexity/tests -v
```

La version initiale a passé **34 tests hors ligne** couvrant les phases, la reprise, les empreintes, les erreurs du provider, l’isolation, les verrous, les budgets et les verdicts. Un essai séparé sur une petite tâche a aussi validé le workflow local en préservant les modifications existantes.

**L’appel réel à Antigravity n’a pas été vérifié dans l’environnement de création**, où `agy` est absent. Exécuter `doctor` et une vraie review sur la machine cible pour valider le login, le modèle, le quota et les restrictions locales.

## Documentation

- [Instructions du skill](codexity/SKILL.md)
- [Commandes, installation et récupération](codexity/references/workflow.md)
- [Configuration et protocole Antigravity](codexity/references/antigravity.md)
- [Périmètre et isolation](codexity/references/security.md)

Le dépôt contient le skill, le runner en Python standard, les prompts et les tests. Il ne contient ni identifiants de compte ni historique privé d’exécution.
