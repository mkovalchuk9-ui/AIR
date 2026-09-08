"""
Builds the daily HTML report and sends it by email via SMTP.
Credentials come from environment variables (GitHub Actions secrets):
  SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, REPORT_TO_EMAIL

Works with Gmail (use an App Password, not your regular password),
or any other SMTP provider (SendGrid, Resend, your own mail server, etc.)
"""

import os
import smtplib
import logging
from datetime import date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import config
from analyzer import Flagged

logger = logging.getLogger("tiktok_scout.reporter")


def build_html(flagged: list[Flagged]) -> str:
    today = date.today().isoformat()

    if not flagged:
        return f"""
        <h2>TikTok Scout — {today}</h2>
        <p>No spikes flagged today. This is normal in the first few days while
        artist history builds up (an artist needs at least
        {config.MIN_HISTORY_POINTS} prior observations before we can judge
        "higher than normal").</p>
        """

    rows = ""
    for f in flagged:
        link = f'<a href="{f.video_url}">view</a>' if f.video_url else ""
        rows += f"""
        <tr>
            <td>@{f.creator_handle}</td>
            <td>{f.market or ""}</td>
            <td>{f.genre_tag or ""}</td>
            <td>{f.view_count:,}</td>
            <td>{f.baseline_avg:,}</td>
            <td>{f.multiple}x</td>
            <td>{f.unsigned_confidence}</td>
            <td>{link}</td>
        </tr>
        """

    return f"""
    <h2>TikTok Scout — {today}</h2>
    <p>{len(flagged)} artist(s) flagged with a video performing well above their normal range.
    "Unsigned confidence" is a heuristic based on bio text — spot-check before reaching out.</p>
    <table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse;font-family:sans-serif;font-size:14px;">
        <tr style="background:#f0f0f0;">
            <th>Artist</th><th>Market</th><th>Genre</th><th>Views</th>
            <th>Normal Avg</th><th>Spike</th><th>Signed Confidence</th><th>Link</th>
        </tr>
        {rows}
    </table>
    """


def send_report(flagged: list[Flagged]) -> None:
    smtp_host = os.environ.get("SMTP_HOST")
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    smtp_user = os.environ.get("SMTP_USER")
    smtp_pass = os.environ.get("SMTP_PASS")
    to_email = os.environ.get("REPORT_TO_EMAIL")

    missing = [
        name for name, val in [
            ("SMTP_HOST", smtp_host), ("SMTP_USER", smtp_user),
            ("SMTP_PASS", smtp_pass), ("REPORT_TO_EMAIL", to_email),
        ] if not val
    ]
    if missing:
        raise RuntimeError(f"Missing required email env vars: {', '.join(missing)}")

    html = build_html(flagged)
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"{config.EMAIL_SUBJECT_PREFIX} — {date.today().isoformat()}"
    msg["From"] = smtp_user
    msg["To"] = to_email
    msg.attach(MIMEText(html, "html"))

    with smtplib.SMTP(smtp_host, smtp_port) as server:
        server.starttls()
        server.login(smtp_user, smtp_pass)
        server.sendmail(smtp_user, [to_email], msg.as_string())

    logger.info("Report emailed to %s", to_email)
