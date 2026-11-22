import os
import smtplib
from enum import StrEnum
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from dotenv import load_dotenv

load_dotenv()

ARCHIVE_DIR = "archive"
EMAIL_AVAILABLE = False


class DeliveryStatus(StrEnum):
    SENT = "sent"
    SKIPPED = "skipped"
    FAILED = "failed"


def email_enabled():
    return EMAIL_AVAILABLE and os.getenv("ENABLE_EMAIL", "false").strip().lower() in {"1", "true", "yes"}


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
    """Archive the digest locally before considering optional delivery."""
    save_to_archive(digest_text)
    save_html_to_archive(html_digest)

    if not email_enabled():
        return DeliveryStatus.SKIPPED

    sender = os.getenv("EMAIL_ADDRESS")
    password = os.getenv("EMAIL_PASSWORD")
    recipient = os.getenv("RECIPIENT_EMAIL") or sender
    if not sender or not password:
        print("  ERROR: Email credentials are missing.")
        return DeliveryStatus.FAILED

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

        smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
        smtp_port = int(os.getenv("SMTP_PORT", "465"))

        if smtp_port == 465:
            with smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=15) as server:
                server.login(sender, password)
                server.sendmail(sender, recipient, msg.as_string())
        else:
            with smtplib.SMTP(smtp_host, smtp_port, timeout=15) as server:
                server.ehlo()
                server.starttls()
                server.ehlo()
                server.login(sender, password)
                server.sendmail(sender, recipient, msg.as_string())

        print("Digest sent to your inbox.")
        return DeliveryStatus.SENT
    except smtplib.SMTPAuthenticationError:
        print(
            "  ERROR: Gmail authentication failed. Check EMAIL_ADDRESS and EMAIL_PASSWORD in .env."
        )
    except (smtplib.SMTPException, OSError, ValueError):
        print("  ERROR: SMTP delivery failed.")
    return DeliveryStatus.FAILED


def send_failure_email(error_text):
    """Send a failure notification only when delivery is enabled."""
    if not email_enabled():
        return DeliveryStatus.SKIPPED
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

        smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
        smtp_port = int(os.getenv("SMTP_PORT", "465"))

        if smtp_port == 465:
            with smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=15) as server:
                server.login(sender, password)
                server.sendmail(sender, recipient, msg.as_string())
        else:
            with smtplib.SMTP(smtp_host, smtp_port, timeout=15) as server:
                server.ehlo()
                server.starttls()
                server.ehlo()
                server.login(sender, password)
                server.sendmail(sender, recipient, msg.as_string())
    except (smtplib.SMTPException, OSError, ValueError):
        print("  WARNING: SMTP failure notification failed.")
