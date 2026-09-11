import os
import json
import uuid
import smtplib
import hashlib
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from flask import Flask, render_template, jsonify, request
from aws_billing import get_billing_data

app = Flask(__name__)

BASE_DIR = os.path.dirname(__file__)
CRON_FILE = os.path.join(BASE_DIR, "cron_jobs.json")
USERS_FILE = os.path.join(BASE_DIR, "users.json")
SMTP_FILE = os.path.join(BASE_DIR, "smtp_config.json")


def hash_password(password):
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


# ==========================================
# USERS STORAGE & AUTHENTICATION
# ==========================================

def load_users():
    if not os.path.exists(USERS_FILE):
        default_users = [
            {
                "id": "usr-1",
                "email": "jigal.prajapati@bytestechnolab.com",
                "name": "Jigal Prajapati",
                "password_hash": hash_password("admin123"),
                "role": "Super Admin",
                "created_at": "2026-09-01 10:00:00"
            },
            {
                "id": "usr-2",
                "email": "admin@bytestechnolab.com",
                "name": "Cloud Admin",
                "password_hash": hash_password("admin123"),
                "role": "Administrator",
                "created_at": "2026-09-05 12:00:00"
            }
        ]
        save_users(default_users)
        return default_users
    try:
        with open(USERS_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return []


def save_users(users):
    with open(USERS_FILE, "w") as f:
        json.dump(users, f, indent=2)


# ==========================================
# CRON JOBS STORAGE
# ==========================================

def load_cron_jobs():
    if not os.path.exists(CRON_FILE):
        default_jobs = [
            {
                "id": "cron-1",
                "name": "Weekly Executive Cost Digest",
                "email": "jigal.prajapati@bytestechnolab.com",
                "schedule": "weekly",
                "cron_expr": "0 9 * * 1",
                "time": "09:00 AM (Every Monday)",
                "report_type": "executive",
                "format": "html",
                "active": True,
                "is_one_time": False,
                "last_run": "2026-09-08 09:00:00",
                "next_run": "2026-09-15 09:00:00"
            },
            {
                "id": "cron-2",
                "name": "Daily Velocity & Spike Monitor",
                "email": "devops-alerts@bytestechnolab.com",
                "schedule": "daily",
                "cron_expr": "0 8 * * *",
                "time": "08:00 AM (Daily)",
                "report_type": "daily_velocity",
                "format": "html",
                "active": True,
                "is_one_time": False,
                "last_run": "2026-09-10 08:00:00",
                "next_run": "2026-09-11 08:00:00"
            }
        ]
        save_cron_jobs(default_jobs)
        return default_jobs
    try:
        with open(CRON_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return []


def save_cron_jobs(jobs):
    with open(CRON_FILE, "w") as f:
        json.dump(jobs, f, indent=2)


# ==========================================
# SMTP CONFIG STORAGE & EMAIL SENDER
# ==========================================

def load_smtp_config():
    if not os.path.exists(SMTP_FILE):
        default_smtp = {
            "host": "",
            "port": 587,
            "username": "",
            "password": "",
            "sender_email": "",
            "use_tls": True,
            "configured": False
        }
        save_smtp_config(default_smtp)
        return default_smtp
    try:
        with open(SMTP_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {"configured": False}


def save_smtp_config(config):
    with open(SMTP_FILE, "w") as f:
        json.dump(config, f, indent=2)


def send_real_email(recipient, subject, html_content, csv_content=None, csv_filename="aws_billing_report.csv"):
    """Dispatches a real email via configured SMTP server."""
    smtp_cfg = load_smtp_config()
    host = smtp_cfg.get("host")
    port = int(smtp_cfg.get("port") or 587)
    username = smtp_cfg.get("username")
    password = smtp_cfg.get("password")
    sender = smtp_cfg.get("sender_email") or username

    if not host or not username or not password or not sender:
        return {
            "success": False,
            "smtp_configured": False,
            "error": "SMTP server credentials are not configured yet. Please configure your SMTP server (e.g. Gmail App Password, AWS SES, or Outlook) in Settings -> SMTP Mail Server."
        }

    try:
        msg = MIMEMultipart("mixed")
        msg["From"] = f"AWS Billing Optimizer <{sender}>"
        msg["To"] = recipient
        msg["Subject"] = subject

        # HTML Body
        html_part = MIMEText(html_content, "html")
        msg.attach(html_part)

        # Optional CSV attachment
        if csv_content:
            attachment = MIMEApplication(csv_content.encode("utf-8"))
            attachment.add_header("Content-Disposition", "attachment", filename=csv_filename)
            msg.attach(attachment)

        # Connect and send
        if port == 465:
            server = smtplib.SMTP_SSL(host, port, timeout=15)
        else:
            server = smtplib.SMTP(host, port, timeout=15)
            if smtp_cfg.get("use_tls", True):
                server.starttls()

        server.login(username, password)
        server.sendmail(sender, [recipient], msg.as_string())
        server.quit()

        return {
            "success": True,
            "smtp_configured": True,
            "message": f"Report successfully dispatched to {recipient} via {host}:{port}."
        }
    except Exception as e:
        return {
            "success": False,
            "smtp_configured": True,
            "error": f"Failed to send email via SMTP ({host}): {str(e)}"
        }


# ==========================================
# CORE ROUTES
# ==========================================

@app.route("/")
def dashboard():
    return render_template("dashboard.html")


@app.route("/api/billing", methods=["POST"])
def billing():
    try:
        data = request.get_json() or {}
        access_key = data.get("access_key")
        secret_key = data.get("secret_key")
        region = data.get("region", "us-east-1")

        if not access_key or not secret_key:
            return jsonify({
                "success": False,
                "error": "AWS Access Key and Secret Access Key are required."
            }), 400

        billing_data = get_billing_data(
            access_key,
            secret_key,
            region
        )

        return jsonify({
            "success": True,
            "data": billing_data
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# ==========================================
# USER AUTHENTICATION APIS
# ==========================================

@app.route("/api/auth/register", methods=["POST"])
def auth_register():
    try:
        data = request.get_json() or {}
        email = data.get("email", "").strip().lower()
        name = data.get("name", "").strip()
        password = data.get("password", "").strip()

        if not email or not password:
            return jsonify({"success": False, "error": "Email and password are required."}), 400

        users = load_users()
        for u in users:
            if u.get("email", "").lower() == email:
                return jsonify({"success": False, "error": "An account with this email already exists."}), 400

        new_user = {
            "id": "usr-" + str(uuid.uuid4())[:8],
            "email": email,
            "name": name or email.split("@")[0].capitalize(),
            "password_hash": hash_password(password),
            "role": "Cloud Operator",
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        users.append(new_user)
        save_users(users)

        return jsonify({
            "success": True,
            "message": "Account created successfully.",
            "user": {
                "id": new_user["id"],
                "email": new_user["email"],
                "name": new_user["name"],
                "role": new_user["role"]
            }
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/auth/login", methods=["POST"])
def auth_login():
    try:
        data = request.get_json() or {}
        email = data.get("email", "").strip().lower()
        password = data.get("password", "").strip()

        if not email or not password:
            return jsonify({"success": False, "error": "Please provide both email and password."}), 400

        users = load_users()
        pwd_hash = hash_password(password)

        for u in users:
            if u.get("email", "").lower() == email:
                if u.get("password_hash") == pwd_hash:
                    return jsonify({
                        "success": True,
                        "message": "Login successful.",
                        "user": {
                            "id": u["id"],
                            "email": u["email"],
                            "name": u["name"],
                            "role": u.get("role", "User")
                        }
                    })
                else:
                    return jsonify({"success": False, "error": "Incorrect password."}), 401

        # If user not found, allow quick auto-registration for convenience
        new_user = {
            "id": "usr-" + str(uuid.uuid4())[:8],
            "email": email,
            "name": email.split("@")[0].replace(".", " ").title(),
            "password_hash": pwd_hash,
            "role": "Cloud Admin",
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        users.append(new_user)
        save_users(users)

        return jsonify({
            "success": True,
            "message": "Account created and logged in.",
            "user": {
                "id": new_user["id"],
                "email": new_user["email"],
                "name": new_user["name"],
                "role": new_user["role"]
            }
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/auth/forgot-password", methods=["POST"])
def auth_forgot_password():
    try:
        data = request.get_json() or {}
        email = data.get("email", "").strip().lower()
        new_password = data.get("new_password", "").strip()

        if not email:
            return jsonify({"success": False, "error": "Please enter your email."}), 400

        users = load_users()
        user_found = False
        for u in users:
            if u.get("email", "").lower() == email:
                if new_password:
                    u["password_hash"] = hash_password(new_password)
                user_found = True
                break

        if user_found:
            save_users(users)
            return jsonify({
                "success": True,
                "message": f"Password has been reset successfully for {email}. You can now sign in."
            })
        return jsonify({"success": False, "error": "No account registered with this email."}), 404
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ==========================================
# SMTP SETTINGS APIS
# ==========================================

@app.route("/api/admin/smtp", methods=["GET"])
def get_smtp_settings():
    cfg = load_smtp_config()
    safe_cfg = {
        "host": cfg.get("host", ""),
        "port": cfg.get("port", 587),
        "username": cfg.get("username", ""),
        "sender_email": cfg.get("sender_email", ""),
        "use_tls": cfg.get("use_tls", True),
        "configured": bool(cfg.get("host") and cfg.get("username"))
    }
    return jsonify({"success": True, "config": safe_cfg})


@app.route("/api/admin/smtp", methods=["POST"])
def save_smtp_settings():
    try:
        data = request.get_json() or {}
        cfg = {
            "host": data.get("host", "").strip(),
            "port": int(data.get("port") or 587),
            "username": data.get("username", "").strip(),
            "password": data.get("password", "").strip(),
            "sender_email": data.get("sender_email", "").strip() or data.get("username", "").strip(),
            "use_tls": bool(data.get("use_tls", True)),
            "configured": bool(data.get("host") and data.get("username"))
        }
        save_smtp_config(cfg)
        return jsonify({"success": True, "message": "SMTP configuration saved successfully."})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/admin/smtp/test", methods=["POST"])
def test_smtp_connection():
    try:
        data = request.get_json() or {}
        test_email = data.get("test_email", "").strip()
        if not test_email:
            return jsonify({"success": False, "error": "Please specify a test email address."}), 400

        html_body = """
        <div style="font-family:Arial,sans-serif; background:#0b101c; color:#f4f4f5; padding:24px; border-radius:12px;">
            <h2 style="color:#00c0f0;">AWS Billing Dashboard PRO - SMTP Test</h2>
            <p>This is a verified test email from your AWS Billing Dashboard. Your SMTP server is configured and working!</p>
            <p style="color:#94a3b8; font-size:12px;">Timestamp: """ + datetime.now().strftime("%Y-%m-%d %H:%M:%S") + """</p>
        </div>
        """
        result = send_real_email(test_email, "AWS Billing Dashboard - SMTP Verification Test", html_body)
        return jsonify(result)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ==========================================
# CRONTAB AUTOMATION APIS (WITH CUSTOM TIME)
# ==========================================

@app.route("/api/admin/cron", methods=["GET"])
def get_cron_jobs():
    jobs = load_cron_jobs()
    return jsonify({"success": True, "jobs": jobs})


@app.route("/api/admin/cron", methods=["POST"])
def create_cron_job():
    try:
        data = request.get_json() or {}
        email = data.get("email", "").strip()
        name = data.get("name", "Custom AWS Report").strip()
        schedule = data.get("schedule", "daily")
        report_type = data.get("report_type", "executive")
        report_format = data.get("format", "html")
        custom_time = data.get("time", "").strip()
        is_one_time = bool(data.get("is_one_time", False))
        one_time_date = data.get("one_time_date", "")

        if not email:
            return jsonify({"success": False, "error": "Recipient email is required."}), 400

        # Construct timing label & expression
        if is_one_time:
            time_label = f"One-Time on {one_time_date} at {custom_time or '09:00 AM'}"
            cron_expr = "ONCE"
        elif schedule == "custom":
            cron_expr = data.get("cron_expr", "0 9 * * *")
            time_label = f"Custom Schedule ({cron_expr}) at {custom_time or '09:00 AM'}"
        else:
            cron_map = {
                "daily": "0 8 * * *",
                "weekly": "0 9 * * 1",
                "monthly": "0 0 1 * *",
                "hourly": "0 * * * *"
            }
            cron_expr = cron_map.get(schedule, "0 8 * * *")
            time_label = f"{custom_time or '08:00 AM'} ({schedule.capitalize()})"

        new_job = {
            "id": "cron-" + str(uuid.uuid4())[:8],
            "name": name,
            "email": email,
            "schedule": schedule,
            "cron_expr": cron_expr,
            "time": time_label,
            "report_type": report_type,
            "format": report_format,
            "active": True,
            "is_one_time": is_one_time,
            "one_time_date": one_time_date,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "last_run": "Never",
            "next_run": "Scheduled"
        }

        jobs = load_cron_jobs()
        jobs.insert(0, new_job)
        save_cron_jobs(jobs)

        return jsonify({
            "success": True,
            "message": f"Crontab automation '{name}' scheduled for {email} ({time_label}).",
            "job": new_job
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/admin/cron/toggle/<job_id>", methods=["POST"])
def toggle_cron_job(job_id):
    jobs = load_cron_jobs()
    target = None
    for j in jobs:
        if j.get("id") == job_id:
            j["active"] = not j.get("active", True)
            target = j
            break
    if target:
        save_cron_jobs(jobs)
        state_str = "activated" if target["active"] else "paused"
        return jsonify({"success": True, "message": f"Job '{target.get('name')}' {state_str}.", "job": target})
    return jsonify({"success": False, "error": "Job not found."}), 404


@app.route("/api/admin/cron/<job_id>", methods=["DELETE"])
def delete_cron_job(job_id):
    jobs = load_cron_jobs()
    new_jobs = [j for j in jobs if j.get("id") != job_id]
    if len(new_jobs) < len(jobs):
        save_cron_jobs(new_jobs)
        return jsonify({"success": True, "message": "Crontab job deleted successfully."})
    return jsonify({"success": False, "error": "Job not found."}), 404


@app.route("/api/admin/cron/run-now/<job_id>", methods=["POST"])
def run_cron_now(job_id):
    jobs = load_cron_jobs()
    target = None
    for j in jobs:
        if j.get("id") == job_id:
            j["last_run"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            target = j
            break
    if target:
        save_cron_jobs(jobs)
        # Attempt real email dispatch if SMTP configured
        html_report = f"""
        <div style="font-family:Arial,sans-serif; background:#0b101c; color:#f4f4f5; padding:24px; border-radius:12px;">
            <h2 style="color:#00c0f0;">AWS Scheduled Cost Report: {target.get('name')}</h2>
            <p>Your automated schedule triggered on {target['last_run']}.</p>
            <p>Schedule: {target.get('time')}</p>
        </div>
        """
        email_res = send_real_email(target.get("email"), f"Automated AWS Report: {target.get('name')}", html_report)
        if email_res.get("success"):
            return jsonify({"success": True, "message": f"Report '{target.get('name')}' emailed to {target.get('email')}!"})
        else:
            return jsonify({"success": True, "message": f"Triggered '{target.get('name')}'. (SMTP note: {email_res.get('error', 'SMTP not configured')})"})
    return jsonify({"success": False, "error": "Job not found."}), 404


# =======================================================
# CUSTOM DATA RANGE REPORT & REAL EMAIL DISPATCH
# =======================================================

@app.route("/api/admin/reports/send-custom", methods=["POST"])
def send_custom_report():
    try:
        data = request.get_json() or {}
        recipient = data.get("recipient", "").strip()
        date_from = data.get("date_from", "")
        date_to = data.get("date_to", "")
        selected_services = data.get("services", [])
        subject = data.get("subject") or f"AWS Custom Cost Report ({date_from} to {date_to})"
        notes = data.get("notes", "")
        html_content = data.get("html_content")
        csv_content = data.get("csv_content")

        if not recipient:
            return jsonify({"success": False, "error": "Recipient email address is required."}), 400

        # Construct styled HTML if not provided directly
        if not html_content:
            svc_rows = "".join([f"<li><strong>{s}</strong></li>" for s in selected_services])
            html_content = f"""
            <div style="font-family:Inter,-apple-system,sans-serif; background:#0b101c; color:#f4f4f5; padding:30px; border-radius:14px;">
                <div style="border-bottom:2px solid #00c0f0; padding-bottom:12px; margin-bottom:18px;">
                    <h2 style="color:#00c0f0; margin:0;">AWS Infrastructure Custom Cost Report</h2>
                    <p style="color:#94a3b8; font-size:12px; margin-top:4px;">Period: {date_from} &rarr; {date_to} &bull; Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}</p>
                </div>
                <div style="background:#111a2e; padding:16px; border-radius:10px; margin-bottom:18px;">
                    <p style="color:#f4f4f5; margin:0;">{notes or 'Please find attached the selected AWS infrastructure billing dimensions.'}</p>
                </div>
                <h4 style="color:#f4f4f5; margin-bottom:8px;">Included Dimensions ({len(selected_services)} services):</h4>
                <ul style="color:#94a3b8; line-height:1.8;">
                    {svc_rows}
                </ul>
            </div>
            """

        # Dispatch real email via SMTP
        email_result = send_real_email(recipient, subject, html_content, csv_content=csv_content)

        if email_result.get("success"):
            return jsonify({
                "success": True,
                "sent_live": True,
                "message": f"Custom report successfully sent to {recipient} via SMTP!",
                "details": email_result
            })
        else:
            return jsonify({
                "success": False,
                "smtp_configured": email_result.get("smtp_configured", False),
                "error": email_result.get("error"),
                "message": email_result.get("error")
            })

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


if __name__ == "__main__":
    app.run(
        host="127.0.0.1",
        port=5000,
        debug=True
    )
