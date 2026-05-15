# Reżyser Audio GPT

**Studio d'Enregistrement Hybride pour Drames Audio, Livres Audio et Histoires Interactives**

**Autres versions linguistiques / Other languages:** [English](readme.md) · [Deutsch](readme.de.md) · [Español](readme.es.md) · [Suomi](readme.fi.md) · [Français](readme.fr.md) · [Íslenska](readme.is.md) · [Italiano](readme.it.md) · [Polski](readme.pl.md) · [Русский](readme.ru.md)


Ensemble d'outils autonomes alimentés par l'IA pour l'écriture automatique, la planification, le formatage et la traduction de scripts volumineux, ainsi que pour la conduite de jeux textuels interactifs. Le projet est une application de bureau native (wxPython) conçue dès le départ pour une accessibilité totale aux lecteurs d'écran (NVDA, VoiceOver) et pour fonctionner avec des synthétiseurs vocaux professionnels (TTS). Il fonctionne sans navigateur et sans serveur local — il se lance comme une fenêtre de programme ordinaire.

Version : **15.2.5** · Langues prises en charge nativement (9) : Polski, Deutsch, English, Español, Suomi, Français, Íslenska, Italiano, Русский.


## Modules principaux

L'application combine cinq outils dans une seule fenêtre, commutables par des raccourcis clavier (Ctrl+1 / Ctrl+2 / Ctrl+3 / Ctrl+4 / Ctrl+5) ou par des boutons sur la barre d'outils. Chaque module fonctionne indépendamment, mais tous partagent les packs de dictionnaires du dossier `dictionaries/` (accents, chiffres, modes créatifs AI) et les paramètres centraux.


### 1. Réalisation (Ctrl+1)

Le principal studio pour écrire des pièces radiophoniques et des livres audio. Vous choisissez le mode — Brainstorming, Script (avec des balises `[SFX]`/`[Personnage: émotion]`), Livre audio (prose traditionnelle) — et dirigez le dialogue avec le modèle via le champ Instructions + Livre du Monde + Mémoire à Long Terme :

* **Livre du Monde Multi-projet :** Le système charge automatiquement en arrière-plan les règles dédiées de l'univers (`.md`) en fonction du fichier source actif, assurant une isolation complète (chargement de contexte sans clic).
* **Accumulateur de l'Intrigue :** Algorithme de « mémoire infinie ». Lorsque l'indicateur de mémoire entre en état d'alerte rouge, le système génère automatiquement un résumé de l'intrigue et l'enregistre dans le champ Mémoire à Long Terme.
* **4 modes créatifs :** Chacun des fichiers dans `dictionaries/<jzk>/rezyser/` décrit une « personnalité » distincte du réalisateur AI (Brainstorming, Script, Livre audio, Postproduction des Titres). Vous pouvez ajuster leur tonalité sans programmation — voir le Gestionnaire de Règles ci-dessous.


### 2. Récits (Ctrl+2, deuxième mode principal à partir de v15.0)

Jeux textuels interactifs dirigés par l'IA en tant que moteur narratif. Contrairement à la Mise en Scène (où vous générez un livre audio prêt à l'emploi), les Récits sont une intrigue dynamique tour par tour :

* **Mode Choix :** chaque tour se termine par 3 à 5 options numérotées A-E. Le mode le plus intuitif pour les joueurs aveugles — NVDA lit les options, vous cliquez sur Tab et Entrée.
* **Mode Moindre Mal :** comme le Mode Choix, mais chaque option est moralement, physiquement ou stratégiquement défavorable. À partir de v15.2, une « fiole » supplémentaire — une option de secours numérotée ZÉRO réutilisable, dont les effets sont pseudo-aléatoires (60% nuisibles / 30% perturbant la perception / 10% rarement bénéfiques, distribution forcée par Python, LLM ne peut pas inventer un effet salvateur).
* **Mode Libre :** toute action en texte libre (« j'essaie d'ouvrir la porte »), le moteur propose 1 à 3 suggestions mais n'impose pas de choix.
* **Modèle AI par mode :** Choix et Moindre Mal utilisent gpt-4o (meilleur raisonnement moral), Libre utilise gpt-4o-mini (économie d'improvisation moins coûteuse).


### 3. Polyglotte (Ctrl+3, Traducteur IA + Accents TTS)

* **Traducteur Sécurisé :** Les longs textes sont automatiquement divisés en blocs de 10 000 caractères maximum et traduits séquentiellement. Chaque bloc est immédiatement enregistré dans un fichier caché `.jsonl`. La reprise après l'épuisement des limites de l'API est entièrement automatique.
* **Automatisation NVDA :** Les traductions sont enregistrées sous forme de fichiers `.html` prêts à l'emploi avec une balise linguistique intégrée ou de fichiers `.docx` avec des balises injectées directement dans la structure XML.
* **8 accents locaux :** Possibilité d'imposer intentionnellement un accent cassé pour les synthétiseurs locaux (Tiflotecnia Voices, eSpeak, OneCore) grâce à des règles regex avancées. Accents étrangers pris en charge : anglais, russe (avec translittération en cyrillique), allemand, espagnol, italien, finlandais, islandais, polonais.
* **Mode Chiffreur :** 6 algorithmes locaux de distorsion de texte — de la lecture à l'envers, à la typoglycémie, en passant par le chiffre de César classique. Chacun avec l'alphabet local du pack linguistique (par exemple, le chiffre de César sur un alphabet FR de 35 caractères avec diacritiques).
* **Réparateur de Balises :** Injecte de manière non invasive le code de langue ISO à deux lettres fourni dans les fichiers existants.


### 4. Convertisseur / Architecte d'Audiobooks (Ctrl+4)

* Traite les fichiers bruts `.txt` ou `.docx` pour la navigation par clavier avec NVDA et des systèmes tels que ElevenLabs.
* Convertit automatiquement les mots-clés (Acte, Chapitre, Prologue) en en-têtes "Heading 1" dans le document Word, et nettoie également les balises HTML inutiles et les balises Markdown.
* À partir de la version 15.1, regroupe 5 tours en scènes avec des en-têtes H1 (détection automatique des Histoires) — prépare le fichier généré par le mode Histoires pour une publication traditionnelle d'audiobook.


### 5. Gestionnaire de Règles (Ctrl+5, nouveauté depuis v13.0)

* **Explorateur de dictionnaires sans Python :** Arborescence visuelle de tous les fichiers YAML dans le dossier `dictionaries/` — accents phonétiques, chiffres, modes créatifs du Réalisateur et du Narrateur. Un linguiste ou un traducteur peut parcourir, dupliquer, éditer et supprimer des règles directement depuis l'interface graphique.
* **Créateur de nouvelles règles :** Formulaire avec choix de type (accent, chiffre de substitutions simples, mode Réalisateur, nouvelle langue de base, chiffre algorithmique) créant un modèle YAML prêt à l'emploi, et pour les cas plus complexes, générant une invite formatée à coller dans ChatGPT / Claude.
* **Refactorisation v13.0 — règles dans les YAML :** Tous les accents, chiffres et modes AI, qui jusqu'à la version 12.0 étaient intégrés comme des constantes "codées en dur" dans le code Python, ont été transférés vers des fichiers déclaratifs `.yaml` chargés dynamiquement au démarrage de l'application. Toute personne capable d'utiliser un éditeur de texte peut ajuster un accent (par exemple, remplacer `sz → sh` par `sz → sch`), ajouter une nouvelle langue, voire modifier le ton de l'invite système pour l'AI — sans compiler le code.


## Multilinguisme (9 langues nativement)

À partir de la version 14.0, l'application prend en charge nativement 9 langues de base : Polski, Deutsch, English, Español, Suomi, Français, Íslenska, Italiano, Русский. Chaque paquet `dictionaries/<code>/` contient des diacritiques, un alphabet et des règles phonétiques opérant sur le texte dans cette langue spécifique — l'application détecte automatiquement la langue source grâce au détecteur de langue lingua (par paragraphe) et charge le paquet approprié pour chaque fragment individuellement.

Toute l'interface GUI, la documentation (`docs/manual.<iso>.txt`) et la plupart des messages système sont disponibles nativement dans chacune des langues prises en charge. Les invites système AI dans les modes Réalisateur et Histoire sont écrites dans les langues cibles (manuellement, non traduites automatiquement — voir `dictionaries/<code>/rezyser/` et `dictionaries/<code>/opowiesci/`).


## Architecture de l'IA et modèles utilisés

L'application répartit intelligemment les tâches, optimisant les coûts et la rapidité d'exécution de l'API OpenAI :

* **gpt-4o :** Le moteur principal de l'application. Il est responsable des tâches génératives lourdes : réalisation de scripts, écriture de prose traditionnelle (Livre audio), modes Choix et Moindre Mal dans les Histoires, génération de résumés et traductions avancées avec maintien du contexte multi-blocs.
* **gpt-4o-mini :** Modèle auxiliaire rapide et léger. Utilisé en arrière-plan pour les micro-tâches nécessitant une grande rapidité : attribution itérative de titres littéraires aux chapitres générés, extraction de codes ISO, mode Libre dans les Histoires (économie d'improvisation de texte libre moins coûteuse).


### Limitations connues des modèles (Anti-Closure)

Malgré l'implémentation de directives systémiques rigoureuses visant à couper les actions aux moments de tension (dite directive Anti-Closure), les modèles LLM contemporains possèdent une forte tendance innée à « clore » les histoires. Cela se traduit souvent par l'insertion de conclusions indésirables, de morales ou de faux « happy ends », en particulier en Mode Livre Audio Traditionnel.

C'est une limitation fondamentale de la génération actuelle d'intelligence artificielle. Pour cette raison, l'application enregistre les projets dans des fichiers texte ordinaires, faciles à éditer (`.txt`). Cela nécessite que l'utilisateur assume le rôle de monteur vivant — en supprimant occasionnellement et manuellement les phrases « de clôture » générées par l'IA, avant de recharger le fichier et de poursuivre le travail.


## Installation et démarrage

### Pour les utilisateurs finaux (Windows)

1. Téléchargez la dernière version depuis l'onglet **Releases** (paquet marqué comme *Latest*) — le fichier `Rezyser_Audio_v<numéro>_Installer.exe`. Lancez-le par un double-clic. L'installateur s'installe par défaut dans le répertoire local de votre compte (`%LocalAppData%\Programs\Reżyser Audio GPT`) et ne nécessite pas de droits administratifs ; vous pouvez choisir votre propre chemin avec le bouton « Parcourir ». Une fois terminé, il crée des raccourcis dans le Menu Démarrer et sur le bureau, et ouvre éventuellement le manuel d'utilisation dans l'éditeur par défaut de fichiers `.txt`.
2. **Configuration de l'API OpenAI :** Lors du premier lancement, l'application signalera l'absence de clé dans la section System Check. Cliquez sur le bouton visible pour générer le fichier `golden_key.env`, ouvrez-le dans un éditeur de texte et collez votre clé (commençant par `sk-proj-`).
3. **Premiers pas :** Ouvrez le fichier `docs/manual.pl.txt` (ou dans une autre langue) dans le dossier d'installation — c'est un manuel d'utilisation complet rédigé dans un langage accessible à tous les utilisateurs, pas seulement aux développeurs.


### Pour les développeurs (clone + configuration)

1. Clonez le dépôt sur votre disque.
2. Exécutez le fichier `setup_dev.bat` pour créer automatiquement un environnement virtuel (`.venv/`) et télécharger les dépendances de `requirements.txt`.
3. Lancez l'application avec la commande `python main.py` ou via le fichier `run_dev.bat`.

Les scripts `.sh` pour macOS/Linux ont été supprimés dans la version 13.1 — l'environnement de développement est concentré sur Windows en raison des spécificités des tests d'accessibilité NVDA. Travailler avec le code sur d'autres systèmes est possible, mais nécessite une configuration manuelle : `python -m venv .venv && .venv/bin/pip install -r requirements.txt`.

**Les scripts de construction des paquets de release** (`build_release.py`, `installer.iss`) sont uniquement destinés à créer des paquets pour Windows. Ils nécessitent un dossier spécial `runtime/` avec une version portable de Python — ce dossier n'est délibérément pas inclus dans le dépôt (il est dans `.gitignore`).


## Documentation complète

Ce README est uniquement un aperçu architectural du projet. Pour découvrir les techniques avancées de prévention des hallucinations de l'IA, les instructions d'installation des synthétiseurs vocaux compatibles (Tiflotecnia Voices, OneCore, eSpeak, Apple Voices), une description complète des modes Histoires avec fiole, ainsi qu'un guide utilisateur complet, consultez les fichiers dans le dossier `docs/` :

* `docs/manual.<iso>.txt` — le manuel principal (écrit pour l'utilisateur final).
* `docs/tales.<iso>.txt` — le manuel du mode Histoires (jeux textuels interactifs).
* `docs/dictionaries.<iso>.txt` — guide pour les linguistes sans Python, sur comment ajouter des accents/chiffres/modes IA personnalisés.

Chacun de ces fichiers est disponible en 9 langues — suffixe `.<iso>.txt` (par exemple, `manual.pl.txt`, `manual.en.txt`, `manual.de.txt`).
