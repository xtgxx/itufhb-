import time
import os
import requests
from yt_dlp import YoutubeDL
from pyrogram.types import Message

from config import MAX_FILE_SIZE, PROXIES, PROXY_URL, COOKIES_FILE
from utils.progress import edit_progress_message


def human_filename_from_cd(cd_header: str | None) -> str | None:
    if not cd_header:
        return None
    if "filename=" not in cd_header:
        return None
    part = cd_header.split("filename=", 1)[1]
    if ";" in part:
        part = part.split(";", 1)[0]
    return part.strip().strip('"').strip("'")


def head_info(url: str, timeout: int = 10):
    """
    HEAD request (proxy ke through):
    - content-length
    - content-type
    - content-disposition filename
    """
    try:
        r = requests.head(
            url,
            allow_redirects=True,
            timeout=timeout,
            proxies=PROXIES,
        )
        size = int(r.headers.get("content-length", 0) or 0)
        ctype = r.headers.get("content-type", "") or ""
        cd = r.headers.get("content-disposition", "") or ""
        filename = human_filename_from_cd(cd)
        return size, ctype, filename
    except Exception:
        return 0, "", None


def is_video_ext(name: str) -> bool:
    ext = name.lower()
    return ext.endswith((".mp4", ".mkv", ".avi", ".mov", ".webm"))


async def download_direct_with_progress(url: str, path: str, progress_msg: Message):
    with requests.get(url, stream=True, proxies=PROXIES) as r:
        r.raise_for_status()
        total = int(r.headers.get("content-length", 0))
        downloaded = 0
        last_edit = time.time()

        with open(path, "wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 1024):
                if not chunk:
                    continue
                f.write(chunk)
                downloaded += len(chunk)
                now = time.time()
                if now - last_edit > 2:
                    await edit_progress_message(progress_msg, "⬇️ Downloading...", downloaded, total)
                    last_edit = now

    await edit_progress_message(progress_msg, "✅ Download complete.", downloaded, total)
    return path, downloaded


def get_formats(url: str):
    """
    yt-dlp se formats + approx size.
    MAX_FILE_SIZE ke hisab se filter.
    """
    ydl_opts = {
        "quiet": True,
        "skip_download": True,
    }
    if PROXY_URL:
        ydl_opts["proxy"] = PROXY_URL
    if os.path.exists(COOKIES_FILE):
        ydl_opts["cookiefile"] = COOKIES_FILE

    with YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        fmts = info.get("formats", [])
        out = []
        for f in fmts:
            if f.get("vcodec") == "none" or f.get("acodec") == "none":
                continue
            ext = f.get("ext")
            if ext not in ("mp4", "webm", "mkv"):
                continue
            height = f.get("height")
            size = f.get("filesize") or f.get("filesize_approx") or 0
            if size and size > MAX_FILE_SIZE:
                continue
            out.append({
                "format_id": f.get("format_id"),
                "ext": ext,
                "height": height,
                "filesize": size,
            })
        out.sort(key=lambda x: (x["height"] or 0), reverse=True)
        return out, info


def download_with_ytdlp(url: str, fmt_id: str, outtmpl: str) -> str:
    ydl_opts = {
        "format": fmt_id,
        "outtmpl": outtmpl,
        "noplaylist": True,
    }
    if PROXY_URL:
        ydl_opts["proxy"] = PROXY_URL
    if os.path.exists(COOKIES_FILE):
        ydl_opts["cookiefile"] = COOKIES_FILE

    with YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

    if os.path.exists(outtmpl):
        return outtmpl
    for ext in (".mp4", ".mkv", ".webm"):
        if os.path.exists(outtmpl + ext):
            return outtmpl + ext
    raise FileNotFoundError("File not found after yt-dlp download")
