"""Send the private coverage report by email. Never written to the public website or repository."""
import logging
import os
import smtplib
from email.message import EmailMessage

log = logging.getLogger(__name__)


def coverage_text(day, rows):
    counts = {}
    for r in rows:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    lines = [f"Hegazy Brief coverage report, {day}", "",
             ", ".join(f"{v} {k.lower()}" for k, v in counts.items()), ""]
    lines += [f"{r['id']:<7} {r['status']:<14} {r['title']}: {r['note']}" for r in rows]
    return "\n".join(lines)


def send(day, rows):
    user, pwd, to = os.environ.get("SMTP_USER"), os.environ.get("SMTP_PASS"), os.environ.get("NOTIFY_TO")
    if not (user and pwd and to):
        log.info("Coverage email skipped: SMTP_USER, SMTP_PASS and NOTIFY_TO are not all set.")
        return
    msg = EmailMessage()
    msg["Subject"] = f"Hegazy Brief coverage report: {day}"
    msg["From"], msg["To"] = user, to
    msg.set_content(coverage_text(day, rows))
    try:
        with smtplib.SMTP_SSL(os.environ.get("SMTP_HOST", "smtp.gmail.com"), 465, timeout=60) as s:
            s.login(user, pwd)
            s.send_message(msg)
        log.info("Coverage report emailed to %s", to)
    except Exception as exc:
        log.warning("Coverage email failed: %s", exc)
