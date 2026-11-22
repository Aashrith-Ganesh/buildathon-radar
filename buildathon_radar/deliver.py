import os
import smtplib
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from dotenv import load_dotenv

load_dotenv()

ARCHIVE_DIR = "archive"


def get_date_range():
    """Date-range subtitle spanning the last 6 days."""
    end = datetime.now()
    start = end - timedelta(days=6)
    if start.strftime("%b %Y") == end.strftime("%b %Y"):
        return f"{start.strftime('%b %d')} - {end.strftime('%d, %Y')}"
    elif start.year == end.year:
        return f"{start.strftime('%b %d')} - {end.strftime('%b %d, %Y')}"
    return f"{start.strftime('%b %d, %Y')} - {end.strftime('%b %d, %Y')}"


def save_to_archive(digest_text):
    os.makedirs(ARCHIVE_DIR, exist_ok=True)
    week_label = datetime.now().strftime("%Y-%m-%d")
    filename = f"{ARCHIVE_DIR}/radar_{week_label}.md"
    with open(filename, "w", encoding="utf-8") as f:
        f.write(f"# Buildathon Radar - Week of {week_label}\n\n")
        f.write(digest_text)
    return filename


def save_html_to_archive(html_digest):
    os.makedirs(ARCHIVE_DIR, exist_ok=True)
    week_label = datetime.now().strftime("%Y-%m-%d")
    filename = f"{ARCHIVE_DIR}/radar_{week_label}.html"
    with open(filename, "w", encoding="utf-8") as f:
        f.write(html_digest)
    return filename


def _count_picks(digest_text):
    return digest_text.count("\n### [")


def send_digest(digest_text, html_digest):
    """Archives the digest locally as markdown and HTML, then optionally emails it if configured.
    Returns True when local archive succeeds and (if enabled) email succeeds.
    Does not crash if email credentials are unconfigured."""
    try:
        save_to_archive(digest_text)
        save_html_to_archive(html_digest)
    except Exception as e:
        print(f"  WARNING: Could not save to archive: {e}")

    sender = os.getenv("EMAIL_ADDRESS")
    password = os.getenv("EMAIL_PASSWORD")
    recipient = os.getenv("RECIPIENT_EMAIL") or sender

    if not sender or not password:
        print(
            "  ERROR: EMAIL_ADDRESS or EMAIL_PASSWORD not set in .env, skipping email send."
        )
        return False

    # If testing or dry-run flag or explicit disable
    enable_email = os.getenv("ENABLE_EMAIL", "true").strip().lower() in ("1", "true", "yes")
    if not enable_email:
        print("  INFO: ENABLE_EMAIL is false; skipping email send. Local reports saved in archive/.")
        return True

    try:
        pick_count = _count_picks(digest_text)

        msg = MIMEMultipart("alternative")
        msg["Subject"] = (
            f"🛰️ Buildathon Radar | {datetime.now().strftime('%b %d, %Y')} | "
            f"{pick_count} events"
        )
        msg["From"] = f"Buildathon Radar <{sender}>"
        msg["To"] = recipient

        text_part = MIMEText(digest_text, "plain")
        html_part = MIMEText(html_digest, "html")

        msg.attach(text_part)
        msg.attach(html_part)

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(sender, password)
            server.sendmail(sender, recipient, msg.as_string())

        print("Digest sent to your inbox.")
        return True
    except smtplib.SMTPAuthenticationError:
        print(
            "  ERROR: Gmail authentication failed. Check EMAIL_ADDRESS and EMAIL_PASSWORD in .env."
        )
    except smtplib.SMTPException as e:
        print(f"  ERROR: SMTP error, {e}")
    except Exception as e:
        print(f"  ERROR: Failed to send email, {e}")
    return False


def send_failure_email(error_text):
    """Sent on fatal failure if email is configured; logs cleanly otherwise."""
    sender = os.getenv("EMAIL_ADDRESS")
    password = os.getenv("EMAIL_PASSWORD")
    recipient = os.getenv("RECIPIENT_EMAIL") or sender

    if not sender or not password:
        print("  INFO: Failure logged to console; email not configured.")
        return

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = "🛰️ Buildathon Radar | run failed"
        msg["From"] = f"Buildathon Radar <{sender}>"
        msg["To"] = recipient

        body = (
            "The weekly Buildathon Radar run failed with an error:\n\n"
            f"{error_text}\n\n"
            "Check local logs for details."
        )
        msg.attach(MIMEText(body, "plain"))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(sender, password)
            server.sendmail(sender, recipient, msg.as_string())
    except Exception as e:
        print(f"  WARNING: Could not send failure email: {e}")
