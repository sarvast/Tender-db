"""
Telegram Bot Notifier for GeM Auto-Tracker.

Setup:
1. Create a bot via @BotFather on Telegram → get BOT_TOKEN
2. Send any message to the bot → go to https://api.telegram.org/bot<TOKEN>/getUpdates → get your CHAT_ID
3. Create a file called .env in this directory:
   TELEGRAM_BOT_TOKEN=your_token_here
   TELEGRAM_CHAT_ID=your_chat_id_here
"""

import os
import requests

# Try to load from .env file (keep secrets out of code)
def _load_env():
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    key, val = line.split("=", 1)
                    os.environ.setdefault(key.strip(), val.strip())

_load_env()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")


def send_telegram_alert(bid_data: dict):
    """
    Sends a Telegram message with key bid details.
    Silently does nothing if token/chat_id not configured.
    """
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return  # Not configured, skip silently

    bid_number = bid_data.get("gem_bid_number", "N/A")
    brand = bid_data.get("category", "General")
    quantity = bid_data.get("quantity", 1)
    department = (bid_data.get("department_name") or "N/A")[:80]
    items = ""
    item_cats = bid_data.get("item_categories")
    if isinstance(item_cats, list):
        items = ", ".join(item_cats)[:100]
    elif item_cats:
        items = str(item_cats)[:100]

    emd = bid_data.get("emd_amount")
    emd_str = f"₹{emd:,.0f}" if emd else "Nil/NA"

    end_date = bid_data.get("bid_end_date")
    if end_date:
        # It's already an ISO string at this point
        try:
            from datetime import datetime
            dt = datetime.fromisoformat(str(end_date))
            end_date_str = dt.strftime("%d %b %Y %H:%M")
        except:
            end_date_str = str(end_date)[:16]
    else:
        end_date_str = "N/A"

    doc_url = bid_data.get("document_url", "")
    pdf_line = f"\n📄 [View Document]({doc_url})" if doc_url else ""

    message = (
        f"🚨 *New GeM Bid Alert!*\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"📌 *{bid_number}*\n"
        f"🏷️ Brand: `{brand}`\n"
        f"📦 Qty: `{quantity}`\n"
        f"💰 EMD: `{emd_str}`\n"
        f"⏰ Ends: `{end_date_str}`\n"
        f"🏢 Dept: _{department}_\n"
        f"🔬 Items: _{items}_"
        f"{pdf_line}"
    )

    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        resp = requests.post(url, json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True
        }, timeout=8)
        if resp.status_code != 200:
            print(f"[Telegram] Failed: {resp.text[:200]}")
    except Exception as e:
        print(f"[Telegram] Error: {e}")
