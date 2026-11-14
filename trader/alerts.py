"""Phone alerts via a private Telegram bot. Falls back to printing if not configured.

Setup (5 minutes): message @BotFather in Telegram, create a bot, copy its token; send
your bot one message, then open https://api.telegram.org/bot<TOKEN>/getUpdates to find
your chat id. Put both in the .env file as TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID.
The bot can only message you; it cannot place trades or read anything.
"""

from __future__ import annotations

import json
import os
import urllib.request


def notify(text: str, level: str = "info") -> bool:
    prefix = {"info": "", "trade": "💱 ", "warn": "⚠️ ", "error": "🛑 "}.get(level, "")
    msg = f"{prefix}[Trader] {text}"
    print(msg)
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat = os.environ.get("TELEGRAM_CHAT_ID")
    if not (token and chat):
        return False
    try:
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=json.dumps({"chat_id": chat, "text": msg}).encode(),
            headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=10).read()
        return True
    except Exception as exc:  # an alert failure must never crash the bot
        print(f"[Trader] alert failed: {exc}")
        return False
