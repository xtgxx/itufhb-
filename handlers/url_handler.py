import os
import re
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton

from database import (
    get_user_doc, is_banned, update_stats,
)
from utils.downloader import (
    get_formats, download_direct_with_progress, download_with_ytdlp,
    head_info,
)
from utils.uploader import upload_with_thumb_and_progress
from utils.progress import human_readable
from config import MAX_FILE_SIZE

URL_REGEX = r"https?://[^\s]+"
PENDING_DOWNLOAD = {}  # chat_id -> state


def split_url_and_name(text: str):
    parts = text.split("|", 1)
    url_part = parts[0].strip()
    custom_name = parts[1].strip() if len(parts) > 1 else None
    return url_part, custom_name


def safe_filename(name: str) -> str:
    name = "".join(c for c in name if c not in "\\/:*?\"<>|")
    return name or "file"


def is_ytdlp_site(url: str) -> bool:
    return True  # jitni site yt-dlp support kare


def register_url_handlers(app: Client):

    @app.on_message(filters.private & filters.text & ~filters.command(
        ["start",
         "setthumb", "delthumb", "showthumb",
         "setcaption", "delcaption", "showcaption",
         "myplan",
         "spoiler_on", "spoiler_off",
         "screens_on", "screens_off",
         "sample_on", "sample_off", "setsample",
         "setprefix", "setsuffix",
         "rename",
         "setpremium", "delpremium", "setlimit",
         "userstats", "users", "stats", "ban", "unban",
         "broadcast", "banlist"]
    ))
    async def handle_url(_, message: Message):
        user_id = message.from_user.id
        if is_banned(user_id):
            return

        user = get_user_doc(user_id)
        limit_c = user["daily_count_limit"]
        limit_s = user["daily_size_limit"]
        used_c = user["used_count_today"]
        used_s = user["used_size_today"]

        # Count limit check
        if limit_c and limit_c > 0 and used_c >= limit_c:
            await message.reply_text(
                f"⛔ Aaj ka upload count limit khatam.\n"
                f"Used: {used_c}/{limit_c}\n"
                "Admin se contact karo ya premium ke liye request karo."
            )
            return

        text = message.text.strip()
        url_candidate, custom_name = split_url_and_name(text)
        match = re.search(URL_REGEX, url_candidate)
        if not match:
            await message.reply_text("⚠️ Koi valid `http/https` URL nahi mila.\nBas URL ya `URL | new_name.mp4` bhejein.")
            return

        url = match.group(0)
        wait_msg = await message.reply_text("🔍 Link deep scan ho raha hai (`HEAD` + `yt-dlp`)...")

        # HEAD info
        head_size, head_ctype, head_fname = head_info(url)

        remaining_size = None
        if limit_s and limit_s > 0:
            remaining_size = max(limit_s - used_s, 0)

        if head_size > 0:
            if head_size > MAX_FILE_SIZE:
                await wait_msg.edit_text(
                    f"⛔ Single file size bohot bada hai.\n"
                    f"Size: {human_readable(head_size)} (> per-file limit)"
                )
                return
            if remaining_size is not None and head_size > remaining_size:
                await wait_msg.edit_text(
                    "⛔ Aaj ka **daily size limit** exceed ho jayega is file se.\n"
                    f"Remain: {human_readable(remaining_size)}, File: {human_readable(head_size)}"
                )
                return
            await wait_msg.edit_text(
                f"ℹ️ Early size check: {human_readable(head_size)}\n"
                "Ab formats check ho rahe hain (yt-dlp)..."
            )

        # yt-dlp formats
        try:
            formats, info = get_formats(url) if is_ytdlp_site(url) else ([], None)
        except Exception:
            formats, info = [], None

        if formats:
            title = info.get("title", head_fname or "video")

            # Agar user ke paas remaining_size hai to uske hisaab se formats filter karo
            filtered = []
            for f in formats:
                size = f.get("filesize") or 0
                if size and size > MAX_FILE_SIZE:
                    continue
                if remaining_size is not None and size and size > remaining_size:
                    continue
                filtered.append(f)

            use_formats = filtered if filtered else formats  # agar filter ke baad khali hua to original use

            PENDING_DOWNLOAD[message.chat.id] = {
                "url": url,
                "custom_name": custom_name,
                "title": title,
                "formats": use_formats,
                "user_id": user_id,
            }

            buttons = []
            for f in use_formats:
                h = f["height"] or "?"
                size_str = human_readable(f["filesize"]) if f["filesize"] else "?"
                buttons.append([
                    InlineKeyboardButton(
                        f"{h}p {f['ext']} ({size_str})",
                        callback_data=f"fmt_{f['format_id']}"
                    )
                ])

            buttons.append([
                InlineKeyboardButton("🌐 Direct URL se try karo", callback_data="direct_dl")
            ])

            await wait_msg.edit_text(
                "🎥 Video/streaming site detect hui.\nQuality choose karo:",
                reply_markup=InlineKeyboardMarkup(buttons),
            )
            return

        # Direct download mode
        await wait_msg.edit_text("🌐 Direct file download mode...")

        filename = head_fname or url.split("/")[-1] or "file"
        if len(filename) > 64:
            filename = "file_from_url"
        if custom_name:
            filename = custom_name
        filename = safe_filename(filename)

        temp_path = filename
        progress_msg = await message.reply_text("⬇️ Downloading...")

        try:
            path, downloaded_bytes = await download_direct_with_progress(
                url, temp_path, progress_msg
            )
            file_size = os.path.getsize(path)
            if file_size > MAX_FILE_SIZE:
                await message.reply_text("❌ File Telegram limit se badi hai, upload nahi ho sakti.")
                os.remove(path)
                return

            if remaining_size is not None and file_size > remaining_size:
                await message.reply_text(
                    "⛔ Aaj ka daily size limit exceed ho jayega is file se.\n"
                    f"Remain: {human_readable(remaining_size)}, File: {human_readable(file_size)}"
                )
                os.remove(path)
                return

            update_stats(downloaded=downloaded_bytes, uploaded=0)
            await upload_with_thumb_and_progress(app, message, path, user_id, progress_msg)

        except Exception as e:
            await message.reply_text(f"❌ Error: `{e}`")
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except Exception:
                    pass

    @app.on_callback_query()
    async def callbacks(client: Client, query):
        data = query.data
        chat_id = query.message.chat.id

        if chat_id not in PENDING_DOWNLOAD:
            await query.answer("⏱ Time out. Dubara URL bhejo.", show_alert=True)
            return

        state = PENDING_DOWNLOAD[chat_id]
        url = state["url"]
        custom_name = state["custom_name"]
        formats = state["formats"]
        title = state["title"]
        user_id = state["user_id"]
        msg = query.message

        user = get_user_doc(user_id)
        limit_c = user["daily_count_limit"]
        limit_s = user["daily_size_limit"]
        used_c = user["used_count_today"]
        used_s = user["used_size_today"]
        remaining_size = None
        if limit_s and limit_s > 0:
            remaining_size = max(limit_s - used_s, 0)

        if limit_c and limit_c > 0 and used_c >= limit_c:
            await msg.edit_text(
                f"⛔ Count limit exceed: {used_c}/{limit_c}\n"
                "Dubara kal try karo."
            )
            del PENDING_DOWNLOAD[chat_id]
            return

        if data == "direct_dl":
            await query.answer("Direct download mode...", show_alert=False)
            del PENDING_DOWNLOAD[chat_id]

            filename = safe_filename(f"{title}.mp4")
            if custom_name:
                filename = safe_filename(custom_name)

            progress_msg = await msg.edit_text("⬇️ Direct download try ho raha hai...")
            try:
                path, downloaded_bytes = await download_direct_with_progress(
                    url, filename, progress_msg
                )
            except Exception as e:
                await msg.edit_text(f"❌ Direct download fail: `{e}`")
                if os.path.exists(filename):
                    os.remove(filename)
                return

            file_size = os.path.getsize(path)
            if file_size > MAX_FILE_SIZE:
                await msg.edit_text("❌ File Telegram limit se badi hai, upload nahi ho sakti.")
                os.remove(path)
                return

            if remaining_size is not None and file_size > remaining_size:
                await msg.edit_text(
                    "⛔ Daily size limit exceed ho jayega is file se.\n"
                    f"Remain: {human_readable(remaining_size)}, File: {human_readable(file_size)}"
                )
                os.remove(path)
                return

            update_stats(downloaded=downloaded_bytes, uploaded=0)
            await upload_with_thumb_and_progress(client, msg, path, user_id, progress_msg)
            return

        if data.startswith("fmt_"):
            fmt_id = data.split("_", 1)[1]
            await query.answer(f"Format: {fmt_id}")
            del PENDING_DOWNLOAD[chat_id]

            # format size check (agar info hai to)
            fmt_size = 0
            for f in formats:
                if f["format_id"] == fmt_id:
                    fmt_size = f.get("filesize") or 0
                    break

            if remaining_size is not None and fmt_size and fmt_size > remaining_size:
                await msg.edit_text(
                    "⛔ Daily size limit exceed ho sakta hai is quality se.\n"
                    f"Remain: {human_readable(remaining_size)}, Format: {human_readable(fmt_size)}"
                )
                return

            filename = safe_filename(f"{title}.mp4")
            if custom_name:
                filename = safe_filename(custom_name)

            await msg.edit_text(f"⬇️ `{fmt_id}` quality me download ho raha hai... (yt-dlp)")
            tmp_name = "temp_ytdlp_video"

            try:
                path = download_with_ytdlp(url, fmt_id, tmp_name)
                final_path = filename
                os.replace(path, final_path)
                path = final_path
            except Exception as e:
                await msg.edit_text(f"❌ yt-dlp download fail: `{e}`")
                if os.path.exists(tmp_name):
                    os.remove(tmp_name)
                return

            file_size = os.path.getsize(path)
            if file_size > MAX_FILE_SIZE:
                await msg.edit_text("❌ File Telegram limit se badi hai, upload nahi ho sakti.")
                os.remove(path)
                return

            if remaining_size is not None and file_size > remaining_size:
                await msg.edit_text(
                    "⛔ Daily size limit exceed ho jayega is file se.\n"
                    f"Remain: {human_readable(remaining_size)}, File: {human_readable(file_size)}"
                )
                os.remove(path)
                return

            update_stats(downloaded=0, uploaded=0)
            progress_msg = await msg.edit_text("📤 Upload start ho raha hai...")
            await upload_with_thumb_and_progress(client, msg, path, user_id, progress_msg)
