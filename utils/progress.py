import math
from pyrogram.types import Message


def human_readable(size: int) -> str:
    if size == 0:
        return "0B"
    units = ["B", "KB", "MB", "GB", "TB"]
    i = int(math.floor(math.log(size, 1024)))
    p = math.pow(1024, i)
    s = round(size / p, 2)
    return f"{s}{units[i]}"


async def edit_progress_message(msg: Message, prefix: str, done: int, total: int):
    if total <= 0:
        percent = 0
    else:
        percent = done * 100 // total
    text = f"{prefix} **{percent}%**\n\nDone: {human_readable(done)} / {human_readable(total)}"
    try:
        await msg.edit_text(text)
    except Exception:
        pass
