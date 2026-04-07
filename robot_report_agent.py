"""
Robot Report Daily News Agent
==============================
Récupère les dernières news du RSS feed de The Robot Report,
les résume via l'API Gemini (Google), et les envoie par mail.

Dépendances : pip install feedparser google-genai python-dotenv
Configuration : renseigner les variables dans la section CONFIG ci-dessous.

Planification (Windows) : utiliser le Planificateur de tâches
"""

import sys
import feedparser
import smtplib
from datetime import datetime, timezone, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from google import genai
from dotenv import load_dotenv
import os

sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

load_dotenv()

CONFIG = {
    "gemini_api_key": os.getenv("GEMINI_API_KEY"),
    "gemini_model": "gemini-2.5-flash-lite",
    "smtp_user": os.getenv("SMTP_USER"),
    "smtp_password": os.getenv("SMTP_PASSWORD"),
    "smtp_host": "smtp.gmail.com",
    "smtp_port": 587,
    "email_from": os.getenv("EMAIL_FROM"),
    "email_to": os.getenv("EMAIL_TO"),
    "email_subject": "🤖 Robot Report Digest — {date}",
    "rss_url": "https://www.therobotreport.com/feed/",
    "hours_back": 24,
    "max_articles": 10,
}

# ─────────────────────────────────────────────


def fetch_recent_articles(rss_url: str, hours_back: int, max_articles: int) -> list:
    """Parse le flux RSS et retourne les articles récents."""
    feed = feedparser.parse(rss_url)
    if feed.bozo:
        raise ValueError(f"Erreur de parsing RSS : {feed.bozo_exception}")

    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours_back)
    articles = []

    for entry in feed.entries:
        if hasattr(entry, "published_parsed") and entry.published_parsed:
            pub_dt = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
        else:
            pub_dt = datetime.now(timezone.utc)

        if pub_dt < cutoff:
            continue

        articles.append({
            "title": entry.get("title", "Sans titre"),
            "link": entry.get("link", ""),
            "published": pub_dt.strftime("%d/%m/%Y %H:%M UTC"),
            "summary": entry.get("summary", entry.get("description", "")),
            "tags": [t.term for t in (entry.get("tags") or [])],
        })

        if len(articles) >= max_articles:
            break

    return articles


def summarize_with_gemini(articles: list, api_key: str, model_name: str) -> str:
    """Envoie les articles à Gemini et retourne un digest structuré en HTML."""
    if not articles:
        return "<p>Aucun nouvel article trouvé dans les dernières 24 heures.</p>"

    client = genai.Client(api_key=api_key)

    articles_text = ""
    for i, a in enumerate(articles, 1):
        tags = ", ".join(a["tags"]) if a["tags"] else "—"
        articles_text += (
            f"\n---\nArticle {i}\n"
            f"Titre : {a['title']}\n"
            f"Date : {a['published']}\n"
            f"Tags : {tags}\n"
            f"Lien : {a['link']}\n"
            f"Résumé brut : {a['summary'][:600]}\n"
        )

    prompt = f"""Tu es un assistant spécialisé en robotique et en IA.
Voici {len(articles)} articles publiés aujourd'hui par The Robot Report.

{articles_text}

Génère un digest quotidien en HTML (fragment, sans <html>/<body>) avec :
1. Un titre <h2> "🤖 Robot Report — {len(articles)} articles du jour"
2. Pour chaque article, un bloc <div class="article"> contenant :
   - <h3> avec le titre (lié à l'URL, target="_blank")
   - <p class="meta"> avec la date et les tags
   - <p class="summary"> : 2-3 phrases synthétisant l'essentiel en français,
     en mettant en avant l'innovation ou l'enjeu principal
3. Une section <div class="trends"> "📊 Tendances du jour" listant en 3-5 bullets
   les grands thèmes qui ressortent de l'ensemble des articles.

Style inline CSS uniquement (email-compatible). Utilise une palette sobre :
fond blanc, texte #222, liens #1a6cba, badges tags gris clair (#eee).
Chaque article séparé par une fine ligne horizontale.
Ne génère que le HTML, sans commentaires ni markdown."""

    response = client.models.generate_content(model=model_name, contents=prompt)
    return response.text


def send_email(html_body: str, config: dict) -> None:
    """Envoie le digest par mail via SMTP."""
    date_str = datetime.now().strftime("%d/%m/%Y")
    subject = config["email_subject"].format(date=date_str)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = config["email_from"]
    msg["To"] = config["email_to"]

    text_part = MIMEText(
        "Votre client mail ne supporte pas le HTML. "
        "Consultez la version HTML de ce message.",
        "plain",
        "utf-8",
    )
    html_part = MIMEText(html_body, "html", "utf-8")

    msg.attach(text_part)
    msg.attach(html_part)

    with smtplib.SMTP(config["smtp_host"], config["smtp_port"]) as server:
        server.ehlo()
        server.starttls()
        server.login(config["smtp_user"], config["smtp_password"])
        server.sendmail(config["email_from"], config["email_to"], msg.as_string())


def save_debug_output(html: str, articles: list) -> None:
    """Sauvegarde le résultat localement pour aperçu."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"digest_{timestamp}.html"

    full_html = f"""<!DOCTYPE html>
<html lang="fr"><head>
<meta charset="utf-8">
<title>Robot Report Digest</title>
</head><body style="font-family:sans-serif;max-width:700px;margin:auto;padding:20px">
{html}
<hr>
<p style="color:#999;font-size:12px">
  Généré le {datetime.now().strftime("%d/%m/%Y à %H:%M")} —
  {len(articles)} articles traités
</p>
</body></html>"""

    with open(filename, "w", encoding="utf-8") as f:
        f.write(full_html)
    print(f"  -> Apercu sauvegarde : {filename}")


def main():
    print(f"\n{'='*50}")
    print(f"  Robot Report Agent — {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    print(f"{'='*50}")

    # 1. Récupération des articles
    print(f"\n[RSS] Récupération du flux ({CONFIG['hours_back']}h)...")
    try:
        articles = fetch_recent_articles(
            CONFIG["rss_url"],
            CONFIG["hours_back"],
            CONFIG["max_articles"],
        )
    except Exception as e:
        print(f"  ERREUR RSS : {e}")
        return

    print(f"  OK {len(articles)} article(s) trouvé(s)")

    if not articles:
        print("  Aucun nouvel article. Fin du script.")
        return

    for i, a in enumerate(articles, 1):
        print(f"   {i}. {a['title'][:70]}..." if len(a['title']) > 70 else f"   {i}. {a['title']}")

    # 2. Résumé via Gemini
    print(f"\n[Gemini] Génération du digest ({CONFIG['gemini_model']})...")
    try:
        html_digest = summarize_with_gemini(
            articles,
            CONFIG["gemini_api_key"],
            CONFIG["gemini_model"],
        )
        print("  OK Digest généré")
    except Exception as e:
        print(f"  ERREUR Gemini : {e}")
        return

    # 3. Sauvegarde locale
    save_debug_output(html_digest, articles)

    # 4. Envoi par mail
    print(f"\n[Mail] Envoi à {CONFIG['email_to']}...")
    try:
        send_email(html_digest, CONFIG)
        print("  OK Mail envoyé avec succès")
    except Exception as e:
        print(f"  ERREUR SMTP : {e}")
        print("    (Le digest HTML a quand même été sauvegardé localement)")
        return

    print(f"\n{'='*50}")
    print("  Agent terminé avec succès")
    print(f"{'='*50}\n")


if __name__ == "__main__":
    main()
