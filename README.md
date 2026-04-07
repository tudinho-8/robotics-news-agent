# 🤖 Robot Report Daily News Agent

Dans le cadre de mon métier de tech m&a, j'ai des dossiers de robotique donc je souhaite monter en compétences sur le sujet. 

Je n'ai pas le temps d'aller regarder plusieurs sites tous les jours, donc je veux un agent qui me mâche le travail.  

Voici donc un agent qui scrape les news via RSS + les résume via Gemini AI + les envois tous les matins si ca lui semble intéressant pour moi

## Stack
- `feedparser` — parsing RSS
- `google-genai` — API Gemini
- `python-dotenv` — variables d'environnement

## Installation
```bash
pip install feedparser google-genai python-dotenv
```

## Configuration
Crée un fichier `.env` :
```env
GEMINI_API_KEY=
SMTP_USER=
SMTP_PASSWORD=
EMAIL_FROM=
EMAIL_TO=
```

## Lancement
```bash
python agent.py
```
