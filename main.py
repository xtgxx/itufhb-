from pyrogram import Client
from config import API_ID, API_HASH, BOT_TOKEN
from handlers.start import register_start_handlers
from handlers.user_settings import register_user_settings_handlers
from handlers.admin import register_admin_handlers
from handlers.url_handler import register_url_handlers
from threading import Thread
from flask import Flask

app = Flask('')

@app.route('/')
def home():
    return "Bot is alive", 200

def run():
    app.run(host='0.0.0.0', port=8080)

Thread(target=run).start()


def main():
    app = Client(
        "advanced_uploader_bot",
        api_id=API_ID,
        api_hash=API_HASH,
        bot_token=BOT_TOKEN,
    )

    register_start_handlers(app)
    register_user_settings_handlers(app)
    register_admin_handlers(app)
    register_url_handlers(app)

    print("✅ Advanced Uploader Bot started...")
    app.run()


if __name__ == "__main__":
    main()
