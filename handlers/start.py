from pyrogram import Client, filters
from pyrogram.types import Message
from database import get_user_doc, is_banned
from config import BOT_USERNAME
from utils.progress import human_readable


def register_start_handlers(app: Client):
    @app.on_message(filters.command("start"))
    async def start_cmd(_, message: Message):
        if is_banned(message.from_user.id):
            return

        user = get_user_doc(message.from_user.id)
        limit_count = user.get("daily_count_limit", 0)
        limit_size = user.get("daily_size_limit", 0)
        used_c = user.get("used_count_today", 0)
        used_s = user.get("used_size_today", 0)

        count_status = f"{used_c}/{limit_count}" if limit_count and limit_count > 0 else f"{used_c}/∞"
        size_status = (
            f"{human_readable(used_s)}/{human_readable(limit_size)}"
            if limit_size and limit_size > 0
            else f"{human_readable(used_s)}/∞"
        )

        await message.reply_text(
            f"👋 Namaste {message.from_user.first_name}!\n\n"
            f"Main @{BOT_USERNAME} hoon – Advanced URL Uploader Bot.\n\n"
            "Main kya kar sakta hoon:\n"
            "• Deep scan (yt-dlp) – jitni sites support hoti hain\n"
            "• Direct http/https file download\n"
            "• Quality select (1080p/720p/480p...)\n"
            "• Rename: `URL | newname.mp4`\n"
            "• Telegram file/video rename: `/rename new_name.ext` (reply)\n"
            "• Thumbnail, caption, spoiler, screenshots, sample clip\n"
            "• Prefix/suffix naming, daily count + size limit, premium system\n\n"
            "🖼 Thumbnail: /setthumb, /showthumb, /delthumb\n"
            "✏ Caption: /setcaption, /showcaption, /delcaption\n"
            "🎭 Spoiler: /spoiler_on, /spoiler_off\n"
            "📸 Screenshots: /screens_on, /screens_off\n"
            "🎬 Sample: /sample_on, /sample_off, /setsample 15\n"
            "🔤 Prefix: /setprefix [text_]\n"
            "🔤 Suffix: /setsuffix [_text]\n"
            "📋 Plan: /myplan\n\n"
            f"📊 Count today: {count_status}\n"
            f"📦 Size today: {size_status}",
            disable_web_page_preview=True,
      )
