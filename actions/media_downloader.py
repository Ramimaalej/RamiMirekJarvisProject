import os
import requests
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

def download_media(parameters: dict | None = None, player=None) -> str:
    parameters = parameters or {}
    url = (parameters.get("url") or "").strip()
    media_type = (parameters.get("type") or "image").lower()
    
    if not url:
        return "Please provide a URL to download."
    
    save_dir = Path("downloads")
    save_dir.mkdir(exist_ok=True)
    
    try:
        if media_type == "youtube" or "youtube.com" in url or "youtu.be" in url:
            # Note: requires yt-dlp installed on host
            import subprocess
            cmd = ["yt-dlp", "-f", "best", "-o", str(save_dir / "%(title)s.%(ext)s"), url]
            subprocess.run(cmd, check=True, timeout=300)
            return f"Video downloaded to {save_dir} folder."
        else:
            # Generic file/image download
            filename = url.split("/")[-1].split("?")[0] or "downloaded_file"
            filepath = save_dir / filename
            resp = requests.get(url, stream=True, timeout=30)
            resp.raise_for_status()
            with open(filepath, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)
            return f"Media downloaded: {filename} saved to {save_dir}."
    except Exception as e:
        logger.error("Download error: %s", e)
        return f"Download failed: {str(e)}"
