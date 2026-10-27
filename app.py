import os, requests
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from flask import Flask, request

app = Flask(__name__)
TOKEN = os.environ["TG_TOKEN"]
CHAT_ID = os.environ["TG_CHAT_ID"]
API_KEY = os.environ.get("SELLAUTH_API_KEY", "")
TZ = ZoneInfo(os.environ.get("TIMEZONE", "Europe/Paris"))

def send(text):
    requests.post(
        f"https://api.telegram.org/bot{TOKEN}/sendMessage",
        json={"chat_id": CHAT_ID, "text": text[:4000]},
        timeout=10,
    )

def fetch_invoice(shop_id, invoice_id):
    r = requests.get(
        f"https://api.sellauth.com/v1/shops/{shop_id}/invoices/{invoice_id}",
        headers={"Authorization": f"Bearer {API_KEY}"},
        timeout=15,
    )
    r.raise_for_status()
    j = r.json()
    return j.get("data", j) if isinstance(j, dict) else {}

def fmt_date(s):
    if not s:
        return "?"
    dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    return dt.astimezone(TZ).strftime("%Y-%m-%d %H:%M:%S")

def build(inv):
    msg = (
        "🛒 Nouvelle commande\n"
        f"ID : {inv.get('id')}\n"
        f"Email : {inv.get('email')}\n"
        f"Montant : {inv.get('price')} {inv.get('currency')}\n"
        f"Paiement : {inv.get('gateway')}\n"
        f"Statut : {inv.get('status')}\n"
        f"Date : {fmt_date(inv.get('created_at'))}\n"
    )
    for it in inv.get("items") or []:
        p = it.get("product") or {}
        v = it.get("variant") or {}
        name = it.get("custom_name") or p.get("name") or "?"
        if v.get("name"):
            name += f" {v['name']}"
        msg += f"• {name} x{it.get('quantity', 1)}\n"
    return msg

@app.get("/")
def home():
    return "ok", 200

@app.post("/webhook")
def webhook():
    payload = request.get_json(silent=True) or {}
    shop_id = payload.get("shop_id")
    invoice_id = (payload.get("data") or {}).get("invoice_id")
    try:
        send(build(fetch_invoice(shop_id, invoice_id)))
    except Exception as e:
        send(f"⚠️ Commande #{invoice_id} reçue, erreur : {e}")
    return "ok", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
