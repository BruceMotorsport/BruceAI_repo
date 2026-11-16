import csv
import smtplib
import ssl
import time
import os
import sys
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path

CONFIG = {
    "smtp_server": "smtp.gmail.com",
    "smtp_port": 587,
    "sender_email": os.environ.get("GMAIL_USER", ""),
    "sender_password": os.environ.get("GMAIL_APP_PASSWORD", ""),
    "input_csv": os.environ.get("INPUT_CSV", "contacts.csv"),
    "results_csv": os.environ.get("RESULTS_CSV", "results.csv"),
    "delay_seconds": float(os.environ.get("DELAY_SECONDS", "5")),
    "max_retries": int(os.environ.get("MAX_RETRIES", "3")),
    "dry_run": os.environ.get("DRY_RUN", "false").lower() == "true",
}

EMAIL_TEMPLATE = """Subject: Quick intro — {name} at {company}

Hi {name},

I came across your profile and wanted to reach out. I noticed you're the {role} at {company} — impressive work.

I'm reaching out because I believe there could be a strong fit between what we're building and what {company} is working on. I'd love to set up a brief call to explore whether there's mutual value.

A bit about us: we help companies like {company} streamline their operations and drive measurable growth. I think {notes} makes this particularly relevant for you.

Would you be open to a 15-minute conversation next week?

Best regards,
Bruce

---
Bruce AI | Empire Builder
LinkedIn: {linkedin}
Phone: {phone}
"""


def read_contacts(csv_path: str) -> list[dict]:
    contacts = []
    with open(csv_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            contacts.append({k.strip(): (v.strip() if v else "") for k, v in row.items()})
    return contacts


def load_sent_emails(results_path: str) -> set[str]:
    sent = set()
    if not Path(results_path).exists():
        return sent
    with open(results_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("status") == "success":
                sent.add(row.get("email", "").lower())
    return sent


def send_email(smtp_server: str, smtp_port: int, sender: str, password: str,
               to_email: str, subject: str, body: str) -> tuple[bool, str]:
    msg = MIMEMultipart()
    msg["From"] = sender
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    try:
        context = ssl.create_default_context()
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls(context=context)
            server.login(sender, password)
            server.sendmail(sender, to_email, msg.as_string())
        return True, "sent"
    except smtplib.SMTPAuthenticationError as e:
        return False, f"auth_error: {e}"
    except smtplib.SMTPRecipientsRefused as e:
        return False, f"recipient_refused: {e}"
    except smtplib.SMTPException as e:
        return False, f"smtp_error: {e}"
    except Exception as e:
        return False, f"error: {e}"


def log_result(results_path: str, name: str, email: str, status: str, detail: str):
    file_exists = Path(results_path).exists()
    with open(results_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["timestamp", "name", "email", "status", "detail"])
        writer.writerow([datetime.now().isoformat(), name, email, status, detail])


def validate_config() -> list[str]:
    errors = []
    if not CONFIG["sender_email"]:
        errors.append("GMAIL_USER env var not set")
    if not CONFIG["sender_password"]:
        errors.append("GMAIL_APP_PASSWORD env var not set")
    if not Path(CONFIG["input_csv"]).exists():
        errors.append(f"Input CSV not found: {CONFIG['input_csv']}")
    return errors


def main():
    errors = validate_config()
    if errors:
        print("Configuration errors:")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)

    contacts = read_contacts(CONFIG["input_csv"])
    sent_emails = load_sent_emails(CONFIG["results_csv"])

    print(f"Loaded {len(contacts)} contacts from {CONFIG['input_csv']}")
    print(f"Already sent: {len(sent_emails)} (will skip)")
    print(f"Dry run: {CONFIG['dry_run']}")
    print(f"Delay between emails: {CONFIG['delay_seconds']}s")
    print("-" * 60)

    success_count = 0
    fail_count = 0
    skip_count = 0

    for i, contact in enumerate(contacts, 1):
        name = contact.get("name", "")
        email = contact.get("email", "")
        phone = contact.get("phone", "")
        company = contact.get("company", "")
        role = contact.get("role", "")
        linkedin = contact.get("linkedin", "")
        notes = contact.get("notes", "")

        if not email:
            print(f"[{i}/{len(contacts)}] SKIP — no email for '{name}'")
            skip_count += 1
            continue

        if email.lower() in sent_emails:
            print(f"[{i}/{len(contacts)}] SKIP — already sent to {email}")
            skip_count += 1
            continue

        subject = f"Quick intro — {name} at {company}"
        body = EMAIL_TEMPLATE.format(
            name=name, company=company, role=role,
            linkedin=linkedin, phone=phone, notes=notes
        )

        if CONFIG["dry_run"]:
            print(f"[{i}/{len(contacts)}] DRY RUN — would send to {email}")
            print(f"  Subject: {subject}")
            print(f"  Body preview: {body[:120]}...")
            success_count += 1
            continue

        sent = False
        last_error = ""
        for attempt in range(1, CONFIG["max_retries"] + 1):
            ok, detail = send_email(
                CONFIG["smtp_server"], CONFIG["smtp_port"],
                CONFIG["sender_email"], CONFIG["sender_password"],
                email, subject, body
            )
            if ok:
                sent = True
                break
            last_error = detail
            if attempt < CONFIG["max_retries"]:
                wait = CONFIG["delay_seconds"] * attempt
                print(f"  Retry {attempt}/{CONFIG['max_retries']} after {wait}s — {detail}")
                time.sleep(wait)

        if sent:
            log_result(CONFIG["results_csv"], name, email, "success", "sent")
            print(f"[{i}/{len(contacts)}] SENT — {email}")
            success_count += 1
        else:
            log_result(CONFIG["results_csv"], name, email, "failed", last_error)
            print(f"[{i}/{len(contacts)}] FAILED — {email} — {last_error}")
            fail_count += 1

        if i < len(contacts):
            time.sleep(CONFIG["delay_seconds"])

    print("-" * 60)
    print(f"Done. Sent: {success_count} | Failed: {fail_count} | Skipped: {skip_count}")
    print(f"Results logged to: {CONFIG['results_csv']}")


if __name__ == "__main__":
    main()
