from flask import Flask, request, jsonify
from jinja2 import Environment, FileSystemLoader, TemplateNotFound
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from flask_cors import CORS
import smtplib
import logging
import json
import os
import html

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

# === Load allowed sites with error handling ===
try:
    with open("allowed_sites.json") as f:
        allowed_sites = json.load(f)
except Exception as e:
    raise RuntimeError(f"❌ Failed to load allowed_sites.json: {e}")

# === Load SMTP credentials with error handling ===
try:
    with open("smtp_credentials.json") as f:
        smtp_credentials = json.load(f)
except Exception as e:
    raise RuntimeError(f"❌ Failed to load smtp_credentials.json: {e}")

# === CORS domain whitelist ===
origin_map = {
    site_id: domain
    for site_id, domain in allowed_sites.items()
}

def cors_origin_validator(origin):
    return origin in origin_map.values()

CORS(app, origins=cors_origin_validator)

# === Jinja2 setup ===
env = Environment(loader=FileSystemLoader("templates"))

@app.route("/submit-form", methods=["POST"])
def submit_form():
    data = request.form
    site_id = data.get("site_id")

    if site_id not in allowed_sites:
        logging.warning(f"Rejected form: unknown site_id '{site_id}'")
        return jsonify({"success": False, "error": "Invalid site ID"}), 400

    creds = smtp_credentials.get(site_id)
    if not creds:
        logging.error(f"No SMTP credentials for site_id '{site_id}'")
        return jsonify({"success": False, "error": "Missing SMTP credentials"}), 500

    smtp_host = creds["host"]
    smtp_port = creds["port"]
    smtp_user = creds["username"]
    smtp_pass = creds["password"]
    smtp_secure = creds.get("secure", "tls")
    recipient_email = creds["recipient_email"]
    from_email = creds.get("from_email", smtp_user)
    from_name = creds.get("from_name", site_id)

    # === Email template logic ===
    template_name = f"{site_id}.html"
    try:
        template = env.get_template(template_name)
        html_content = template.render(data=data)
    except TemplateNotFound:
        template = env.get_template("default.html")
        rows = ""
        for key, value in data.items():
            if key == "site_id":
                continue
            label = html.escape(key.replace("_", " ").capitalize())
            safe_value = html.escape(value).replace("\n", "<br>")
            rows += f"<tr><td><strong>{label}</strong></td><td>{safe_value}</td></tr>"
        html_content = template.render(form_fields=rows)

    # === Compose and send email ===
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"New Contact Form Submission from {site_id}"
    msg["From"] = f"{from_name} <{from_email}>"
    msg["To"] = recipient_email
    msg.attach(MIMEText(html_content, "html"))

    try:
        server = smtplib.SMTP(smtp_host, smtp_port, timeout=10)
        if smtp_secure == "tls":
            server.starttls()
        server.login(smtp_user, smtp_pass)
        server.send_message(msg)
        server.quit()
        logging.info(f"✅ Email sent for site_id: {site_id}")
        return jsonify({"success": True})
    except Exception as e:
        logging.error(f"❌ Email failed: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

# === Start server ===
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
