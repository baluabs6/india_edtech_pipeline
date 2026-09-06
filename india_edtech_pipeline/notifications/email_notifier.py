"""
email_notifier.py
Sends an email alert listing newly-flagged high-risk students, so a school
admin doesn't have to remember to poll /v1/students/at-risk. Uses plain
SMTP (works with Azure Communication Services' SMTP relay, SendGrid, or any
standard mail provider) rather than locking into one vendor's SDK.
"""
import logging
import smtplib
from email.mime.text import MIMEText

import pandas as pd

from config import NOTIFY

logger = logging.getLogger(__name__)


def send_high_risk_alert(newly_high_risk: pd.DataFrame) -> bool:
    """Sends one summary email for all students crossing the risk threshold
    in this scoring run. Returns False (and logs) instead of raising, since a
    failed notification shouldn't fail the whole batch job."""
    if newly_high_risk.empty:
        logger.info("No students crossed the high-risk threshold this run — no alert sent.")
        return True

    if not (NOTIFY.smtp_host and NOTIFY.from_email and NOTIFY.to_emails):
        logger.warning("SMTP not configured (SMTP_HOST/ALERT_FROM_EMAIL/ALERT_TO_EMAILS) — skipping alert email")
        return False

    lines = [
        f"Student {row.student_id} (school {row.school_id}, {row.state}/{row.district}): "
        f"risk score {row.dropout_risk_score:.2f}"
        for row in newly_high_risk.itertuples()
    ]
    body = (
        f"{len(newly_high_risk)} student(s) crossed the high-risk threshold "
        f"({NOTIFY.high_risk_threshold:.0%}) in last night's scoring run:\n\n"
        + "\n".join(lines)
    )

    message = MIMEText(body)
    message["Subject"] = f"[EdTech India] {len(newly_high_risk)} student(s) newly flagged as high dropout risk"
    message["From"] = NOTIFY.from_email
    to_list = [addr.strip() for addr in NOTIFY.to_emails.split(",") if addr.strip()]
    message["To"] = ", ".join(to_list)

    try:
        with smtplib.SMTP(NOTIFY.smtp_host, NOTIFY.smtp_port) as server:
            server.starttls()
            if NOTIFY.smtp_user:
                server.login(NOTIFY.smtp_user, NOTIFY.smtp_password)
            server.sendmail(NOTIFY.from_email, to_list, message.as_string())
        logger.info("Sent high-risk alert email for %d student(s)", len(newly_high_risk))
        return True
    except Exception as e:  # noqa: BLE001 - notification failures must never crash the batch job
        logger.error("Failed to send high-risk alert email: %s", e)
        return False
