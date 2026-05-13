import os
import json
import threading
from datetime import date
from flask import Flask, jsonify, request
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# ── Config ────────────────────────────────────────────────────────────────────
TOKEN = os.environ["TELEGRAM_TOKEN"]
GOAL  = int(os.environ.get("DAILY_GOAL", 8))

# ── In-memory store (resets on redeploy — good enough for daily tracking) ─────
store = {"date": str(date.today()), "count": 0, "log": []}
lock  = threading.Lock()

def reset_if_new_day():
    today = str(date.today())
    if store["date"] != today:
        store.update({"date": today, "count": 0, "log": []})

# ── Telegram bot ──────────────────────────────────────────────────────────────
ADD_WORDS    = {"glass", "add", "water", "drink", "drank", "had", "yes", "yep", "+", "1"}
REMOVE_WORDS = {"undo", "remove", "delete", "oops", "-", "mistake"}

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip().lower()
    with lock:
        reset_if_new_day()
        if any(w in text for w in ADD_WORDS):
            if store["count"] < GOAL:
                store["count"] += 1
                store["log"].append(update.message.date.strftime("%H:%M"))
            pct = int(store["count"] / GOAL * 100)
            bar = "🟦" * store["count"] + "⬜" * (GOAL - store["count"])
            msg = f"{bar}\n{store['count']}/{GOAL} glasses ({pct}%)"
            if store["count"] >= GOAL:
                msg += "\n🎉 Goal reached! Great work!"
        elif any(w in text for w in REMOVE_WORDS):
            if store["count"] > 0:
                store["count"] -= 1
                if store["log"]: store["log"].pop()
                msg = f"↩️ Removed one. Now at {store['count']}/{GOAL} glasses."
            else:
                msg = "Nothing to undo!"
        else:
            msg = (
                f"💧 Water Tracker\n"
                f"Today: {store['count']}/{GOAL} glasses\n\n"
                f"Say 'glass', 'add', or 'drink' to log one.\n"
                f"Say 'undo' to remove the last one."
            )
    await update.message.reply_text(msg)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Hi! I'm your water tracker bot.\n\n"
        "Just send me 'glass', 'add', or 'drink' every time you have a glass of water.\n"
        "Send 'undo' to remove the last one.\n\n"
        f"Your daily goal is {GOAL} glasses. Let's go! 💧"
    )

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with lock:
        reset_if_new_day()
        remaining = GOAL - store["count"]
        bar = "🟦" * store["count"] + "⬜" * (GOAL - store["count"])
        msg = (
            f"{bar}\n"
            f"Today: {store['count']}/{GOAL} glasses\n"
            f"Remaining: {remaining}\n"
            f"Est. volume: {store['count'] * 250} ml"
        )
    await update.message.reply_text(msg)

# ── Flask API (for the water tracker artifact) ────────────────────────────────
api = Flask(__name__)

@api.route("/count")
def get_count():
    with lock:
        reset_if_new_day()
    return jsonify({"count": store["count"], "goal": GOAL, "log": store["log"], "date": store["date"]})

@api.route("/add", methods=["POST"])
def add():
    with lock:
        reset_if_new_day()
        if store["count"] < GOAL:
            from datetime import datetime
            store["count"] += 1
            store["log"].append(datetime.now().strftime("%H:%M"))
    return jsonify({"count": store["count"]})

@api.route("/remove", methods=["POST"])
def remove():
    with lock:
        reset_if_new_day()
        if store["count"] > 0:
            store["count"] -= 1
            if store["log"]: store["log"].pop()
    return jsonify({"count": store["count"]})

# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import asyncio

    # Run Flask in a background thread
    flask_thread = threading.Thread(
        target=lambda: api.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000))),
        daemon=True
    )
    flask_thread.start()

    # Run Telegram bot
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("Bot is running...")
    app.run_polling()
