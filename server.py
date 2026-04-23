from fastapi import FastAPI, Request
import json
import os
import secrets
import resend
from datetime import datetime, timedelta

app = FastAPI()
KEYS_FILE = "keys.json"

def load_keys():
    try:
        with open(KEYS_FILE, "r") as f:
            return json.load(f)
    except:
        return {}

def save_keys(keys):
    with open(KEYS_FILE, "w") as f:
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
    resend.api_key = os.environ.get("RESEND_API_KEY")
    plan_name = "Lifetime" if plan == "lifetime" else "Pro"
    
    try:
        print(f"[EMAIL] Sending to {email}...")
        r = resend.Emails.send({
            "from": "ClickFree AI <onboarding@resend.dev>",
            "to": [email],
            "subject": f"Your ClickFree AI {plan_name} License Key",
            "html": f"""
            <div style="font-family:-apple-system,sans-serif;max-width:500px;margin:0 auto;padding:40px 20px;color:#0a0a0a;">
                <div style="text-align:center;margin-bottom:32px;">
                    <div style="background:#0a0a0a;color:white;width:48px;height:48px;border-radius:12px;display:inline-flex;align-items:center;justify-content:center;font-size:20px;font-weight:700;">CF</div>
                    <h1 style="font-size:22px;font-weight:600;margin:12px 0 0;">ClickFree AI</h1>
                </div>
                <p>Hi {name},</p>
                <p>Thank you for purchasing ClickFree AI {plan_name}! Here is your license key:</p>
                <div style="background:#f5f5f5;border-radius:12px;padding:20px;text-align:center;margin:24px 0;">
                    <code style="font-size:18px;font-weight:600;letter-spacing:2px;">{key}</code>
                </div>
                <h3>How to activate:</h3>
                <ol style="line-height:2;">
                    <li>Download ClickFree AI from <a href="https://zerouipro.vercel.app">zerouipro.vercel.app</a></li>
                    <li>Open the app and go to the <strong>License</strong> tab</li>
                    <li>Enter your key and click <strong>Activate</strong></li>
                    <li>Enjoy {"unlimited" if plan == "lifetime" else "Pro"} access!</li>
                </ol>
                <p style="color:#888;font-size:13px;margin-top:32px;">
                    Need help? Email vivangpt25@gmail.com<br>
                    {"Lifetime license — no renewal needed." if plan == "lifetime" else "Pro license valid for 1 year."}
                </p>
            </div>
            """
        })
        print(f"[EMAIL] Sent! ID: {r}")
    except Exception as e:
        print(f"[EMAIL] Error: {e}")

@app.post("/webhook/gumroad")
async def gumroad_webhook(request: Request):
    try:
        body = await request.form()
        data = dict(body)
        print(f"[WEBHOOK] Received: {json.dumps(data, indent=2)}")
        email = data.get("email", "")
        name = data.get("full_name", "Customer")
        product_name = data.get("product_name", "").lower()
        plan = "lifetime" if "lifetime" in product_name else "pro"
        key = generate_key(plan)
        send_key_email(email, name, key, plan)
        print(f"[WEBHOOK] Done: {plan} key for {email}: {key}")
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
    return {"valid": True, "plan": entry["plan"], "expires_at": entry.get("expires_at"), "message": f"{entry['plan'].title()} activated!"}

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/check-env")
def check_env():
    return {
        "RESEND_API_KEY": "SET" if os.environ.get("RESEND_API_KEY") else "NOT SET"
    }
