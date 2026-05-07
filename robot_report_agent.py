"""
Robotics News Agent
====================
Agrège les flux RSS de plusieurs sources robotique/IA,
résume via Gemini et envoie un digest quotidien par mail.

Dépendances : pip install feedparser google-genai python-dotenv
Configuration : fichier .env (voir .env.example)

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
    "email_to": [a.strip() for a in os.getenv("EMAIL_TO", "").split(",") if a.strip()],
    "email_subject": "🤖 Robotics Digest — {date}",
    "rss_feeds": [
        {"url": "https://www.therobotreport.com/feed/", "source": "The Robot Report"},
        {"url": "https://techcrunch.com/category/robotics/feed/", "source": "TechCrunch Robotics"},
        {"url": "https://www.reddit.com/r/robotics/.rss", "source": "Reddit r/robotics"},
    ],
    "hours_back": 24,
    "max_articles_per_feed": 10,
}

# ─────────────────────────────────────────────


def fetch_from_feed(url: str, source: str, hours_back: int, max_articles: int) -> list:
    """Parse un flux RSS et retourne les articles récents avec leur source."""
    try:
        feed = feedparser.parse(url)
    except Exception as e:
        print(f"  [!] Impossible de lire {source} : {e}")
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours_back)
    articles = []

    for entry in feed.entries:
        if hasattr(entry, "published_parsed") and entry.published_parsed:
            pub_dt = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)  # type: ignore[misc]
        else:
            pub_dt = datetime.now(timezone.utc)

        if pub_dt < cutoff:
            continue

        articles.append({
            "source": source,
            "title": entry.get("title", "Sans titre"),
            "link": entry.get("link", ""),
            "published": pub_dt.strftime("%d/%m/%Y %H:%M UTC"),
            "summary": entry.get("summary", entry.get("description", "")),
            "tags": [t.term for t in (entry.get("tags") or [])],
        })

        if len(articles) >= max_articles:
            break

    return articles


def fetch_all_articles(config: dict) -> list:
    """Agrège les articles de tous les flux RSS configurés."""
    all_articles = []
    for feed in config["rss_feeds"]:
        print(f"  -> {feed['source']}...")
        articles = fetch_from_feed(
            feed["url"],
            feed["source"],
            config["hours_back"],
            config["max_articles_per_feed"],
        )
        print(f"     {len(articles)} article(s)")
        all_articles.extend(articles)
    return all_articles


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
            f"Source : {a['source']}\n"
            f"Titre : {a['title']}\n"
            f"Date : {a['published']}\n"
            f"Tags : {tags}\n"
            f"Lien : {a['link']}\n"
            f"Résumé brut : {a['summary'][:600]}\n"
        )

    prompt = f""" Tu es un rédacteur de veille spécialisé en robotique et IA.
Ta mission est de produire une note de veille quotidienne courte, sélective, premium et utile.
Voici {len(articles)} articles issus de plusieurs sources (The Robot Report, TechCrunch, Reddit r/robotics).

CONTENUS :
{articles_text}

OBJECTIF
Produire un email HTML premium, très lisible, très concis, qui ressemble à une note d’analyste.
Le rendu ne doit jamais ressembler à une liste brute d’articles ou à un flux RSS.

RÈGLES DE SÉLECTION
1. Garde au maximum 5 sujets au total.
2. Priorité absolue à The Robot Report, considéré comme la meilleure source.
3. Garde uniquement les articles réellement intéressants.
4. Pour The Robot Report, conserve seulement les sujets qui apportent une information importante, concrète ou structurante :
   - lancement ou évolution produit significative
   - levée de fonds
   - acquisition, partenariat ou mouvement stratégique
   - certification, conformité, réglementation
   - dataset, framework, publication technique structurante
   - déploiement industriel concret
   - preuve réelle, chiffre, traction, usage
5. Pour Tech Crunch, garde entre 0 et 2 article, uniquement s’ils sont vraiment forts, ou c'est une levée de fonds/un m&a intéressant
6. Pour Reddit, garde entre 0 et 2 posts max, uniquement s’il contient une info sur une levée, une news importante et novatrice, une news qui te parait factuelle et non biaisée.
7. Exclure Reddit si le contenu est :
   - hobbyiste sans portée réelle
   - question ouverte
   - opinion
   - humour
   - gadget
   - bricolage sans résultat significatif
8. Déduplique les sujets proches. Si plusieurs contenus parlent du même sujet, ne garde que la version la plus informative.
9. Il est acceptable de ne retenir que 2, 3 ou 4 sujets si le reste est faible. Ne remplis jamais artificiellement.

CRITÈRES DE JUGEMENT
Pour chaque contenu, évalue implicitement :
- importance réelle
- caractère concret / niveau de preuve
- portée sectorielle
- originalité
- qualité de la source

RÈGLES DE RÉDACTION
1. Tout doit être en français.
2. Réécris chaque titre pour qu’il soit court, naturel, propre et éditorial.
3. Le texte doit être direct et dense.
4. Utilise le moins de mots possible.
5. Pas de remplissage, pas de tournures creuses, pas de paraphrase inutile.
6. Chaque sujet doit tenir en :
   - un titre
   - un résumé très court en 2 phrases maximum
7. Le résumé doit dire :
   - ce qui s’est passé
   - pourquoi cela mérite d’être retenu aujourd’hui
8. Ajoute un bloc d’ouverture “Ce qu’il faut retenir” avec 2 à 4 bullets maximum.
9. N’ajoute aucune section “Tendances du jour”.
10. Le header doit indiquer “{len(articles)} articles analysés”, jamais “sources analysées”.

CONTRAINTES HTML
1. Génère uniquement un fragment HTML.
2. N’ajoute jamais de balises <html>, <head> ou <body>.
3. N’ajoute aucun commentaire.
4. N’ajoute aucun markdown.
5. Utilise uniquement du CSS inline.
6. Respecte exactement la structure HTML ci-dessous.
7. Remplace seulement les contenus textuels et répète le bloc <tr class="item-row"> pour chaque sujet retenu.
8. Le rendu doit être email-compatible, premium, sobre, minimaliste, avec une esthétique inspirée d’Apple :
   - fond clair
   - espace généreux
   - hiérarchie nette
   - texte foncé
   - gris subtil
   - bleu discret pour les liens
   - coins arrondis
   - fines séparations
9. N’utilise pas d’emojis dans les titres d’articles.
10. Un seul emoji est autorisé : 🤖 dans le header.

HTML ATTENDU — À RESPECTER STRICTEMENT

<div style="margin:0;padding:24px 0;background-color:#f5f5f7;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="border-collapse:collapse;background-color:#f5f5f7;margin:0;padding:0;width:100%;">
    <tr>
      <td align="center" style="padding:0 16px;">
        <table role="presentation" width="680" cellpadding="0" cellspacing="0" border="0" style="border-collapse:separate;width:680px;max-width:680px;background:#ffffff;border:1px solid #e5e5e7;border-radius:20px;">
          
          <tr>
            <td style="padding:32px 32px 20px 32px;">
              <div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Arial,sans-serif;font-size:28px;line-height:32px;font-weight:700;color:#111111;letter-spacing:-0.02em;margin:0 0 8px 0;">
                🤖 Robotics Digest
              </div>
              <div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Arial,sans-serif;font-size:13px;line-height:18px;color:#6e6e73;margin:0;">
                [DATE DU DIGEST] · {len(articles)} articles analysés · [X] retenus
              </div>
            </td>
          </tr>

          <tr>
            <td style="padding:0 32px 24px 32px;">
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="border-collapse:separate;width:100%;background:#f9f9fb;border:1px solid #ececf1;border-radius:16px;">
                <tr>
                  <td style="padding:18px 20px 18px 20px;">
                    <div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Arial,sans-serif;font-size:14px;line-height:18px;font-weight:600;color:#111111;margin:0 0 10px 0;">
                      Ce qu’il faut retenir
                    </div>
                    <ul style="margin:0;padding-left:18px;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Arial,sans-serif;font-size:14px;line-height:21px;color:#222222;">
                      [INSÉRER 2 À 4 <li> ULTRA CONCIS]
                    </ul>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <tr>
            <td style="padding:0 32px 8px 32px;">
              <div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Arial,sans-serif;font-size:12px;line-height:16px;font-weight:600;letter-spacing:0.04em;text-transform:uppercase;color:#6e6e73;">
                Sélection
              </div>
            </td>
          </tr>

          <tr>
            <td style="padding:0 32px 32px 32px;">
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="border-collapse:collapse;width:100%;">
                
                <tr class="item-row">
                  <td style="padding:18px 0;border-top:1px solid #ececf1;">
                    <div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Arial,sans-serif;font-size:12px;line-height:16px;color:#6e6e73;margin:0 0 6px 0;">
                      [SOURCE] · [DATE]
                    </div>
                    <div style="margin:0 0 8px 0;">
                      <a href="[URL]" target="_blank" style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Arial,sans-serif;font-size:20px;line-height:26px;font-weight:600;letter-spacing:-0.01em;color:#111111;text-decoration:none;">
                        [TITRE RÉÉCRIT]
                      </a>
                    </div>
                    <div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Arial,sans-serif;font-size:14px;line-height:22px;color:#222222;margin:0 0 10px 0;">
                      [RÉSUMÉ EN 2 PHRASES MAXIMUM]
                    </div>
                    <div>
                      <a href="[URL]" target="_blank" style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Arial,sans-serif;font-size:13px;line-height:18px;font-weight:500;color:#1a6cba;text-decoration:none;">
                        Lire l’article →
                      </a>
                    </div>
                  </td>
                </tr>

              </table>
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>
</div>

RÈGLES FINALES DE SORTIE
- Génère uniquement le HTML final.
- Respecte exactement la structure fournie.
- Répète seulement les blocs nécessaires pour les articles retenus.
- Ne crée pas d’autres sections.
- Ne mets pas de tags ou badges inutiles.
- Ne dépasse pas 5 sujets.
- Si seuls 2 ou 3 sujets sont vraiment bons, n’en affiche que 2 ou 3.
"""

    response = client.models.generate_content(model=model_name, contents=prompt)
    return response.text


def send_email(html_body: str, config: dict) -> None:
    """Envoie le digest par mail via SMTP."""
    date_str = datetime.now().strftime("%d/%m/%Y")
    subject = config["email_subject"].format(date=date_str)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = config["email_from"]
    msg["To"] = ", ".join(config["email_to"])

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
        server.sendmail(config["email_from"], config["email_to"], msg.as_string())  # email_to est une liste


def save_debug_output(html: str, articles: list) -> None:
    """Sauvegarde le résultat localement pour aperçu."""
    filename = "digest_latest.html"

    full_html = f"""<!DOCTYPE html>
<html lang="fr"><head>
<meta charset="utf-8">
<title>Robotics Digest</title>
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
    print(f"  Robotics News Agent — {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    print(f"{'='*50}")

    # 1. Récupération des articles
    sources = [f["source"] for f in CONFIG["rss_feeds"]]
    print(f"\n[RSS] Récupération ({CONFIG['hours_back']}h) — {len(sources)} sources...")
    articles = fetch_all_articles(CONFIG)
    print(f"  Total : {len(articles)} article(s)")

    if not articles:
        print("  Aucun nouvel article. Fin du script.")
        return

    for i, a in enumerate(articles, 1):
        title = a['title'][:70] + "..." if len(a['title']) > 70 else a['title']
        print(f"   {i}. [{a['source']}] {title}")

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
    print(f"\n[Mail] Envoi à {len(CONFIG['email_to'])} destinataire(s) : {', '.join(CONFIG['email_to'])}...")
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
