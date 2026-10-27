import os, json, requests
from flask import Flask, request

app = Flask(__name__)
TOKEN = os.environ["TG_TOKEN"]
CHAT_ID = os.environ["TG_CHAT_ID"]
DEBUG = os.environ.get("DEBUG", "1") == "1"

def send(text):
    requests.post(
        f"https://api.telegram.org/bot{TOKEN}/sendMessage",
        json={"chat_id": CHAT_ID, "text": text[:4000]},
        timeout=10,
    )

def g(d, *keys, default="?"):
    for k in keys:
        if isinstance(d, dict) and k in d:
            d = d[k]
        else:
            return default
    return d

@app.get("/")
def home():
    return "ok", 200

@app.post("/webhook")
def webhook():
    data = request.get_json(silent=True) or {}
    inv = data.get("data", data)

    msg = (
        "🛒 Nouvelle commande\n"
        f"ID : {g(inv, 'id')}\n"
        f"Email : {g(inv, 'email')}\n"
        f"Montant : {g(inv, 'price')} {g(inv, 'currency', default='')}\n"
        f"Paiement : {g(inv, 'gateway')}\n"
        f"Statut : {g(inv, 'status')}\n"
    )
    items = inv.get("items") or inv.get("products") or []
    for it in items:
        msg += f"• {g(it, 'name', 'product')} x{g(it, 'quantity', default=1)}\n"

    send(msg)
    if DEBUG:
        send("DEBUG:\n" + json.dumps(data, indent=1, ensure_ascii=False))
    return "ok", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
