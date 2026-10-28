import os, json, threading, requests
from datetime import datetime
from zoneinfo import ZoneInfo
from flask import Flask, request

app = Flask(__name__)

# ---------- CONFIG ----------
TOKEN = os.environ["TG_TOKEN"]
CHAT_ID = str(os.environ["TG_CHAT_ID"])
API_KEY = os.environ.get("SELLAUTH_API_KEY", "")
SHOP_ID = os.environ.get("SHOP_ID", "")
TZ = ZoneInfo(os.environ.get("TIMEZONE", "Europe/Paris"))
SHOP_URL = "https://uhqshopdiscord.mysellauth.com/"
API = "https://api.sellauth.com/v1"
HEAD = {"Authorization": f"Bearer {API_KEY}"}

HELP = (
    "👋 Bienvenue !\n\n"
    "Commandes disponibles :\n"
    "/stock : voir le stock et les prix"
)

# ---------- ANTI-DOUBLON ----------
SEEN_INVOICES = set()
SEEN_UPDATES = set()
LOCK = threading.Lock()

def first_time(store, key):
    with LOCK:
        if key in store:
            return False
        if len(store) > 500:
            store.clear()
        store.add(key)
        return True

# ---------- TELEGRAM ----------
def send(text, chat_id=None, button=False):
    for i in range(0, len(text), 4000):
        data = {"chat_id": chat_id or CHAT_ID, "text": text[i:i + 4000]}
        if button and i + 4000 >= len(text):
            data["reply_markup"] = {
                "inline_keyboard": [[{"text": "• Buy", "url": SHOP_URL}]]
            }
        requests.post(
            f"https://api.telegram.org/bot{TOKEN}/sendMessage",
            json=data, timeout=10,
        )

# ---------- COMMANDES ----------
def fetch_invoice(shop_id, invoice_id):
    r = requests.get(f"{API}/shops/{shop_id}/invoices/{invoice_id}",
                     headers=HEAD, timeout=15)
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

def process_invoice(shop_id, invoice_id):
    try:
        send(build(fetch_invoice(shop_id, invoice_id)))
    except Exception as e:
        send(f"⚠️ Commande #{invoice_id} reçue, erreur : {e}")

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

def price_of(o):
    for k in ("price", "price_usd", "amount"):
        if o.get(k) not in (None, ""):
            return str(o[k])
    return None

def build_stock():
    products = fetch_products()
    if not products:
        return "Aucun produit trouvé."
    out = "📦 STOCK\n\n"
    for p in products:
        variants = p.get("variants") or []
        if len(variants) > 1:
            out += f"▪️ {p.get('name', '?')}\n"
            for v in variants:
                pr = price_of(v)
                out += f"    - {v.get('name', '?')} : {stock_of(v)} en stock"
                out += f" | {pr} $\n" if pr else "\n"
        else:
            v = variants[0] if variants else {}
            pr = price_of(v) or price_of(p)
            st = stock_of(v) if v else stock_of(p)
            out += f"▪️ {p.get('name', '?')} : {st} en stock"
            out += f" | {pr} $\n" if pr else "\n"
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
    if invoice_id and first_time(SEEN_INVOICES, invoice_id):
        threading.Thread(target=process_invoice,
                         args=(shop_id, invoice_id)).start()
    return "ok", 200

@app.post("/telegram")
def telegram():
    upd = request.get_json(silent=True) or {}
    if not first_time(SEEN_UPDATES, upd.get("update_id")):
        return "ok", 200
    m = upd.get("message") or {}
    chat = str((m.get("chat") or {}).get("id", ""))
    text = (m.get("text") or "").strip().lower().split("@")[0]
    if chat != CHAT_ID:  # seul toi peux utiliser le bot
        return "ok", 200
    try:
        if text == "/start":
            send(HELP, chat)
        elif text == "/stock":
            send(build_stock(), chat, button=True)
        elif text == "/rawstock":  # debug : 1er produit brut
            p = fetch_products()
            send(json.dumps(p[0] if p else {}, indent=1, ensure_ascii=False), chat)
    except Exception as e:
        send(f"⚠️ Erreur : {e}", chat)
    return "ok", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
