from fastapi import FastAPI, Request, BackgroundTasks
import hashlib
import hmac
import json
import os
import smtplib
import secrets
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta

app = FastAPI()

# Keys storage — in production use a database
KEYS_FILE = "keys.json"

def load_keys():
    try:
        with open(KEYS_FILE, 'r') as f:
            return json.load(f)
    except:
        return {}

def save_keys(keys):
    with open(KEYS_FILE, 'w') as f:
        json.dump(keys, f, indent=2)

def generate_key(plan: str) -> str:
    raw = secrets.token_hex(8).upper()
    key = f"CF-{raw[:4]}-{raw[4:8]}-{raw[8:12]}-{raw[12:16]}"
    keys = load_keys()
    
    expires_at = None
    if plan == "pro":
        expires_at = (datetime.now() + timedelta(days=365)).isoformat()
    
    keys[key] = {
        "plan": plan,
        "activated": False,
        "activated_by": None,
        "expires_at": expires_at,
        "created_at": datetime.now().isoformat()
    }
    save_keys(keys)
    return key

def send_key_email(email: str, name: str, key: str, plan: str):
    GMAIL_USER = os.environ.get("GMAIL_USER")
    GMAIL_PASS = os.environ.get("GMAIL_PASS")
    
    if not GMAIL_USER or not GMAIL_PASS:
        print(f"[EMAIL] Would send key {key} to {email}")
        return
    
    plan_name = "Lifetime" if plan == "lifetime" else "Pro"
    
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"Your ClickFree AI {plan_name} License Key"
    msg["From"] = GMAIL_USER
    msg["To"] = email
    
    html = f"""
    <html>
    <body style="font-family: -apple-system, sans-serif; max-width: 500px; margin: 0 auto; padding: 40px 20px; color: #0a0a0a;">
        <div style="text-align: center; margin-bottom: 32px;">
            <div style="background: #0a0a0a; color: white; width: 48px; height: 48px; border-radius: 12px; display: inline-flex; align-items: center; justify-content: center; font-size: 24px; font-weight: 700; margin-bottom: 16px;">CF</div>
            <h1 style="font-size: 24px; font-weight: 600; margin: 0;">ClickFree AI</h1>
        </div>
        
        <p>Hi {name},</p>
        <p>Thank you for purchasing ClickFree AI {plan_name}! Here is your license key:</p>
        
        <div style="background: #f5f5f5; border-radius: 12px; padding: 20px; text-align: center; margin: 24px 0;">
            <code style="font-size: 18px; font-weight: 600; letter-spacing: 2px; color: #0a0a0a;">{key}</code>
        </div>
        
        <h3>How to activate:</h3>
        <ol style="line-height: 2;">
            <li>Download ClickFree AI from <a href="https://zerouipro.vercel.app">zerouipro.vercel.app</a></li>
            <li>Open the app and go to the <strong>License</strong> tab</li>
            <li>Enter your key and click <strong>Activate</strong></li>
            <li>Enjoy {'unlimited' if plan == 'lifetime' else 'Pro'} access!</li>
        </ol>
        
        <p style="color: #888; font-size: 13px; margin-top: 32px;">
            Need help? Reply to this email or contact vivangpt25@gmail.com<br>
            {'This is a lifetime license — no renewal needed.' if plan == 'lifetime' else 'Your Pro license is valid for 1 year.'}
        </p>
    </body>
    </html>
    """
    
    msg.attach(MIMEText(html, "html"))
    
    try:
        print(f"[EMAIL] Attempting to send to {email}...")
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(GMAIL_USER, GMAIL_PASS)
            server.sendmail(GMAIL_USER, email, msg.as_string())
        print(f"[EMAIL] Successfully sent to {email}")
    except smtplib.SMTPAuthenticationError as e:
        print(f"[EMAIL] Auth error - check Gmail app password: {e}")
    except smtplib.SMTPException as e:
        print(f"[EMAIL] SMTP error: {e}")
    except Exception as e:
        print(f"[EMAIL] Unexpected error: {e}")

@app.post("/webhook/gumroad")
async def gumroad_webhook(request: Request, background_tasks: BackgroundTasks):
    try:
        body = await request.form()
        data = dict(body)
        
        print(f"[WEBHOOK] Received: {json.dumps(data, indent=2)}")
        
        # Get buyer info
        email = data.get("email", "")
        name = data.get("full_name", "Customer")
        product_name = data.get("product_name", "").lower()
        
        # Determine plan
        if "lifetime" in product_name:
            plan = "lifetime"
        else:
            plan = "pro"
        
        # Generate and send key
        key = generate_key(plan)
        background_tasks.add_task(send_key_email, email, name, key, plan)
        
        print(f"[WEBHOOK] Generated {plan} key for {email}: {key}")
        return {"success": True}
        
    except Exception as e:
        print(f"[WEBHOOK] Error: {e}")
        return {"success": False, "error": str(e)}

@app.get("/validate/{key}")
async def validate_key(key: str, machine_id: str = ""):
    keys = load_keys()
    
    if key not in keys:
        return {"valid": False, "message": "Invalid key"}
    
    entry = keys[key]
    
    if entry.get("expires_at"):
        expiry = datetime.fromisoformat(entry["expires_at"])
        if datetime.now() > expiry:
            return {"valid": False, "message": "License expired"}
    
    if entry["activated"] and entry.get("activated_by") and entry["activated_by"] != machine_id:
        return {"valid": False, "message": "Key already used on another device"}
    
    if not entry["activated"]:
        keys[key]["activated"] = True
        keys[key]["activated_by"] = machine_id
        keys[key]["activated_at"] = datetime.now().isoformat()
        save_keys(keys)
    
    return {
        "valid": True,
        "plan": entry["plan"],
        "expires_at": entry.get("expires_at"),
        "message": f"{entry['plan'].title()} plan activated!"
    }

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/check-env")
def check_env():
    gmail_user = os.environ.get("GMAIL_USER", "NOT SET")
    gmail_pass = os.environ.get("GMAIL_PASS", "NOT SET")
    return {
        "GMAIL_USER": gmail_user,
        "GMAIL_PASS": "SET" if gmail_pass != "NOT SET" else "NOT SET"
    }
