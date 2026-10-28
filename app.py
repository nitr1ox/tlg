import os, json, requests
from datetime import datetime
from zoneinfo import ZoneInfo
from flask import Flask, request

app = Flask(__name__)
TOKEN = os.environ["TG_TOKEN"]
CHAT_ID = str(os.environ["TG_CHAT_ID"])
API_KEY = os.environ.get("SELLAUTH_API_KEY", "")
SHOP_ID = os.environ.get("SHOP_ID", "")
TZ = ZoneInfo(os.environ.get("TIMEZONE", "Europe/Paris"))
API = "https://api.sellauth.com/v1"
HEAD = {"Authorization": f"Bearer {API_KEY}"}

def send(text, chat_id=None):
    for i in range(0, len(text), 4000):
        requests.post(
            f"https://api.telegram.org/bot{TOKEN}/sendMessage",
            json={"chat_id": chat_id or CHAT_ID, "text": text[i:i+4000]},
            timeout=10,
        )

def fetch_invoice(shop_id, invoice_id):
    r = requests.get(f"{API}/shops/{shop_id}/invoices/{invoice_id}", headers=HEAD, timeout=15)
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

# ---------- STOCK ----------
def fetch_products():
    products, url, params = [], f"{API}/shops/{SHOP_ID}/products", {"perPage": 100}
    for _ in range(20):
        r = requests.get(url, headers=HEAD, params=params, timeout=20)
        r.raise_for_status()
        j = r.json()
        products += j.get("data", []) if isinstance(j, dict) else j
        nxt = j.get("next_page_url") if isinstance(j, dict) else None
        if not nxt:
            break
        url, params = nxt, None
    return products

def stock_of(o):
    for k in ("stock_count", "stock", "stock_amount", "quantity"):
        if k in o and o[k] is not None:
            return o[k]
    return "?"

def build_stock():
    products = fetch_products()
    if not products:
        return "Aucun produit trouvé."
    out = "📦 STOCK\n\n"
    for p in products:
        variants = p.get("variants") or []
        out += f"▪️ {p.get('name', '?')} : {stock_of(p)}\n"
        if len(variants) > 1:
            for v in variants:
                out += f"    - {v.get('name', '?')} : {stock_of(v)}\n"
    return out

# ---------- ROUTES ----------
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

@app.post("/telegram")
def telegram():
    upd = request.get_json(silent=True) or {}
    m = upd.get("message") or {}
    chat = str((m.get("chat") or {}).get("id", ""))
    text = (m.get("text") or "").strip().lower().split("@")[0]
    if chat != CHAT_ID:          # seul toi peux utiliser le bot
        return "ok", 200
    try:
        if text == "/stock":
            send(build_stock(), chat)
        elif text == "/rawstock":  # pour debug : montre le 1er produit brut
            p = fetch_products()
            send(json.dumps(p[0] if p else {}, indent=1, ensure_ascii=False), chat)
    except Exception as e:
        send(f"⚠️ Erreur stock : {e}", chat)
    return "ok", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
