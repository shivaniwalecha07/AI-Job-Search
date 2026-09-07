"""SMTP sender for the digest. Credentials come from Settings (.env), never hard-coded.
Gmail: use an App Password (not your login password) and keep it in .env only.
"""
from __future__ import annotations

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from job_agent.settings import get_settings


def send_email(subject: str, html_body: str) -> None:
    s = get_settings()
    if not (s.smtp_host and s.smtp_user and s.smtp_password and s.digest_to):
        raise RuntimeError("SMTP not configured (set SMTP_* and DIGEST_TO in .env).")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = s.digest_from or s.smtp_user
    msg["To"] = s.digest_to
    msg.attach(MIMEText("Your SWE job digest is attached as HTML.", "plain"))
    msg.attach(MIMEText(html_body, "html"))

    with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=30) as server:
        server.starttls()
        server.login(s.smtp_user, s.smtp_password)
        server.sendmail(msg["From"], [s.digest_to], msg.as_string())
