import os, json, requests
from flask import Flask, request

app = Flask(__name__)
TOKEN = os.environ["TG_TOKEN"]
CHAT_ID = os.environ["TG_CHAT_ID"]
API_KEY = os.environ.get("SELLAUTH_API_KEY", "")
DEBUG = os.environ.get("DEBUG", "1") == "1"

def send(text):
    requests.post(
        f"https://api.telegram.org/bot{TOKEN}/sendMessage",
        json={"chat_id": CHAT_ID, "text": text[:4000]},
        timeout=10,
    )

def first(d, *keys, default="?"):
    for k in keys:
        if isinstance(d, dict) and d.get(k) not in (None, ""):
            return d[k]
    return default

def fetch_invoice(shop_id, invoice_id):
    r = requests.get(
        f"https://api.sellauth.com/v1/shops/{shop_id}/invoices/{invoice_id}",
        headers={"Authorization": f"Bearer {API_KEY}"},
        timeout=15,
    )
    r.raise_for_status()
    return r.json()

@app.get("/")
def home():
    return "ok", 200

@app.post("/webhook")
def webhook():
    payload = request.get_json(silent=True) or {}
    shop_id = payload.get("shop_id")
    invoice_id = (payload.get("data") or {}).get("invoice_id")

    try:
        inv = fetch_invoice(shop_id, invoice_id)
        inv = inv.get("data", inv) if isinstance(inv, dict) else {}
    except Exception as e:
        send(f"⚠️ Commande #{invoice_id} reçue, mais erreur API : {e}")
        return "ok", 200

    msg = (
        "🛒 Nouvelle commande\n"
        f"ID : {first(inv, 'id', default=invoice_id)}\n"
        f"Email : {first(inv, 'email')}\n"
        f"Montant : {first(inv, 'price', 'total', 'amount')} {first(inv, 'currency', default='')}\n"
        f"Paiement : {first(inv, 'gateway', 'payment_method')}\n"
        f"Statut : {first(inv, 'status')}\n"
        f"Date : {first(inv, 'created_at')}\n"
    )
    items = inv.get("items") or inv.get("products") or []
    for it in items:
        name = first(it, 'name') if first(it, 'name') != "?" else first(it.get('product', {}), 'name')
        variant = first(it.get('variant', {}), 'name', default="")
        msg += f"• {name} {variant} x{first(it, 'quantity', default=1)}\n"

    send(msg)
    if DEBUG:
        send("DEBUG:\n" + json.dumps(inv, indent=1, ensure_ascii=False))
    return "ok", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
