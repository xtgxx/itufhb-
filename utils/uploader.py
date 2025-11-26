import os
from pyrogram.client import Client
from pyrogram.types import Message

from utils.progress import edit_progress_message, human_readable
from utils.downloader import is_video_ext
from utils.media_tools import generate_screenshots, generate_sample_clip
from config import MAX_FILE_SIZE, LOG_CHANNEL
from database import get_user_doc, increment_usage, update_stats


async def upload_with_thumb_and_progress(
    app: Client,
    message: Message,
    path: str,
    user_id: int,
    progress_msg: Message,
):
    file_size = os.path.getsize(path)
    if file_size > MAX_FILE_SIZE:
        await message.reply_text("❌ File Telegram limit se badi hai, upload nahi ho sakti.")
        os.remove(path)
        return

    user = get_user_doc(user_id)
    base_name = os.path.basename(path)

    # Prefix / suffix
    prefix = user.get("prefix") or ""
    suffix = user.get("suffix") or ""
    final_name = f"{prefix}{base_name}{suffix}"

    # Caption with {file_name}
    caption_template = user.get("caption")
    if caption_template:
        caption = caption_template.replace("{file_name}", final_name)
    else:
        caption = f"📁 `{final_name}`"

    # Thumbnail
    thumb_path = None
    if user.get("thumb_file_id"):
        try:
            thumb_path = await app.download_media(
                user["thumb_file_id"],
                file_name=f"thumb_{user_id}.jpg"
            )
        except Exception:
            thumb_path = None

    spoiler_flag = bool(user.get("spoiler"))

    # Screenshots
    if user.get("send_screenshots") and is_video_ext(path):
        shots = generate_screenshots(path, out_dir=f"screens_{user_id}", count=3)
        for s in shots:
            try:
                await app.send_photo(
                    chat_id=message.chat.id,
                    photo=s,
                    caption="📸 Video screenshot",
                    has_spoiler=spoiler_flag,
                )
            except Exception:
                pass
            finally:
                if os.path.exists(s):
                    os.remove(s)
        try:
            os.rmdir(f"screens_{user_id}")
        except Exception:
            pass

    # Sample clip
    if user.get("send_sample") and is_video_ext(path):
        sample_duration = int(user.get("sample_duration") or 15)
        sample_path = f"sample_{user_id}.mp4"
        sample = generate_sample_clip(path, sample_path, sample_duration)
        if sample and os.path.exists(sample):
            try:
                await app.send_video(
                    chat_id=message.chat.id,
                    video=sample,
                    caption=f"🎬 Sample clip ({sample_duration}s)",
                    thumb=thumb_path,
                    has_spoiler=spoiler_flag,
                )
            except Exception:
                pass
            finally:
                if os.path.exists(sample):
                    os.remove(sample)

    await message.reply_text("📤 Upload start ho raha hai...")

    async def upload_progress(current, total):
        await edit_progress_message(progress_msg, "📤 Uploading...", current, total)

    try:
        if is_video_ext(path):
            sent = await app.send_video(
                chat_id=message.chat.id,
                video=path,
                file_name=final_name,
                caption=caption,
                thumb=thumb_path,
                has_spoiler=spoiler_flag,
                progress=upload_progress,
            )
        else:
            sent = await app.send_document(
                chat_id=message.chat.id,
                document=path,
                file_name=final_name,
                caption=caption,
                progress=upload_progress,
            )

        # stats & usage
        increment_usage(user_id, file_size)
        update_stats(downloaded=0, uploaded=file_size)

        limit_count = user.get("daily_count_limit", 0)
        limit_size = user.get("daily_size_limit", 0)
        new_used_count = user.get("used_count_today", 0) + 1
        new_used_size = user.get("used_size_today", 0) + file_size

        count_status = (
            f"{new_used_count}/{limit_count}" if limit_count and limit_count > 0
            else f"{new_used_count}/∞"
        )
        size_status = (
            f"{human_readable(new_used_size)}/{human_readable(limit_size)}"
            if limit_size and limit_size > 0
            else f"{human_readable(new_used_size)}/∞"
        )

        await progress_msg.edit_text(
            "✅ Ho gaya!\n"
            f"📊 Count today: {count_status}\n"
            f"📦 Size today: {size_status}\n"
            f"File size: {human_readable(file_size)}"
        )

        if LOG_CHANNEL != 0:
            try:
                text = (
                    f"📥 New upload\n"
                    f"👤 User: `{user_id}`\n"
                    f"💾 Size: {human_readable(file_size)}\n"
                    f"📄 File: `{final_name}`\n"
                    f"💬 Chat: {message.chat.id}"
                )
                await app.send_message(LOG_CHANNEL, text)
            except Exception:
                pass

        return sent
    finally:
        if os.path.exists(path):
            try:
                os.remove(path)
            except Exception:
                pass
        if thumb_path and os.path.exists(thumb_path):
            try:
                os.remove(thumb_path)
            except Exception:
                pass
