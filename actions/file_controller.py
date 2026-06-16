import os
import shutil
import platform
import subprocess
import zipfile
import tarfile
from pathlib import Path
from datetime import datetime

try:
    import send2trash
    _SEND2TRASH = True
except ImportError:
    _SEND2TRASH = False

_OS = platform.system()  # "Windows" | "Darwin" | "Linux"

_SAFE_ROOTS: list[Path] = [
    Path.home(),
    Path("/"),
]

def _is_safe_path(target: Path) -> bool:
    """Verilen path _SAFE_ROOTS içinde mi? Değilse işlemi reddet."""
    try:
        resolved = target.resolve()
        return any(
            resolved == root.resolve() or resolved.is_relative_to(root.resolve())
            for root in _SAFE_ROOTS
        )
    except Exception:
        return False

_XDG_DIRS_CACHE: dict[str, Path] | None = None

def _load_xdg_dirs() -> dict[str, Path]:
    """Parse ~/.config/user-dirs.dirs for localized desktop/download/etc paths."""
    global _XDG_DIRS_CACHE
    if _XDG_DIRS_CACHE is not None:
        return _XDG_DIRS_CACHE
    result: dict[str, Path] = {}
    xdg_file = Path.home() / ".config" / "user-dirs.dirs"
    if xdg_file.is_file():
        try:
            for line in xdg_file.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                m = __import__("re").match(r'^XDG_(\w+)_DIR="?\$HOME/([^"]+)"?', line)
                if m:
                    key = m.group(1).lower()
                    val = Path.home() / m.group(2)
                    if val.exists():
                        result[key] = val
        except Exception:
            pass
    _XDG_DIRS_CACHE = result
    return result

def _xdg(key: str, default: str) -> Path:
    """Get a localised XDG directory, falling back to `default` relative to home."""
    xdg = _load_xdg_dirs().get(key)
    if xdg and xdg.exists():
        return xdg
    return Path.home() / default

def _get_desktop() -> Path:
    if _OS == "Linux":
        xdg = os.environ.get("XDG_DESKTOP_DIR", "")
        if xdg and Path(xdg).exists():
            return Path(xdg)
        return _xdg("desktop", "Desktop")
    return Path.home() / "Desktop"

def _get_downloads() -> Path:
    if _OS == "Linux":
        xdg = os.environ.get("XDG_DOWNLOAD_DIR", "")
        if xdg and Path(xdg).exists():
            return Path(xdg)
        return _xdg("download", "Downloads")
    return Path.home() / "Downloads"

def _get_documents() -> Path:
    if _OS == "Linux":
        xdg = os.environ.get("XDG_DOCUMENTS_DIR", "")
        if xdg and Path(xdg).exists():
            return Path(xdg)
        return _xdg("documents", "Documents")
    return Path.home() / "Documents"

def _get_pictures() -> Path:
    if _OS == "Linux":
        xdg = os.environ.get("XDG_PICTURES_DIR", "")
        if xdg and Path(xdg).exists():
            return Path(xdg)
        return _xdg("pictures", "Pictures")
    return Path.home() / "Pictures"

def _get_music() -> Path:
    if _OS == "Linux":
        xdg = os.environ.get("XDG_MUSIC_DIR", "")
        if xdg and Path(xdg).exists():
            return Path(xdg)
        return _xdg("music", "Music")
    return Path.home() / "Music"

def _get_videos() -> Path:
    if _OS == "Linux":
        xdg = os.environ.get("XDG_VIDEOS_DIR", "")
        if xdg and Path(xdg).exists():
            return Path(xdg)
        return _xdg("videos", "Videos")
    return Path.home() / "Videos"


def _resolve_path(raw: str) -> Path:
    shortcuts: dict[str, Path] = {
        "desktop":   _get_desktop(),
        "downloads": _get_downloads(),
        "documents": _get_documents(),
        "pictures":  _get_pictures(),
        "music":     _get_music(),
        "videos":    _get_videos(),
        "home":      Path.home(),
        "myprojects": Path.home() / "MyProjects",
    }
    lower = raw.strip().lower()
    if lower in shortcuts:
        return shortcuts[lower]

    target = Path(raw).expanduser()
    if target.exists():
        return target

    # Try relative to home directory (e.g. "MyProjects/opencode" → ~/MyProjects/opencode)
    home_target = Path.home() / raw
    if home_target.exists():
        return home_target

    # Case-insensitive fallback — search parent dir for a matching name
    parent = target.parent
    name_lower = target.name.lower()
    if parent.is_dir():
        for child in parent.iterdir():
            if child.name.lower() == name_lower:
                return child

    # Also try case-insensitive for home-relative path
    home_parent = home_target.parent
    if home_parent.is_dir():
        for child in home_parent.iterdir():
            if child.name.lower() == name_lower:
                return child

    return target

def _format_size(b: int) -> str:
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if b < 1024:
            return f"{b:.1f} {unit}"
        b /= 1024
    return f"{b:.1f} TB"

def _safe_trash(target: Path) -> str:

    if not _SEND2TRASH:
        return (
            "send2trash is not installed. "
            "Run: pip install send2trash — "
            "Permanent deletion is disabled for safety."
        )
    send2trash.send2trash(str(target))
    return f"Moved to Trash: {target.name} (previously at {target.resolve()})"


def list_files(path: str = "desktop", show_hidden: bool = False) -> str:
    try:
        target = _resolve_path(path)
        if not _is_safe_path(target):
            return f"Access denied: {target}"
        if not target.exists():
            return f"Path not found: {target}"
        if not target.is_dir():
            return f"Not a directory: {target}"

        items = []
        for item in sorted(target.iterdir()):
            if not show_hidden and item.name.startswith("."):
                continue
            if item.is_dir():
                items.append(f"📁 {item.name}/")
            else:
                size = _format_size(item.stat().st_size)
                items.append(f"📄 {item.name} ({size})")

        if not items:
            return f"Directory is empty: {target.name}/"

        return f"Contents of {target.name}/ ({len(items)} items):\n" + "\n".join(items)

    except PermissionError:
        return f"Permission denied: {path}"
    except Exception as e:
        return f"Error listing files: {e}"


def create_file(path: str, name: str = "", content: str = "") -> str:
    try:
        base   = _resolve_path(path)
        target = (base / name) if name else base
        if not _is_safe_path(target):
            return f"Access denied: {target}"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return f"File created: {target.name} at {target.resolve()}"
    except Exception as e:
        return f"Could not create file: {e}"


def create_folder(path: str, name: str = "") -> str:
    try:
        # Detect OS and set default base to user's home / root directory
        # Windows -> C:\Users\user, Linux/Fedora -> /home/user, Mac -> /Users/user
        if not path or path.lower() in ("desktop", "home"):
            base = Path.home()
        else:
            base = _resolve_path(path)

        target = (base / name) if name else base
        if not _is_safe_path(target):
            return f"Access denied: {target}"

        if target.exists() and not target.is_dir():
            target.unlink()

        # Run directory creation natively using terminal shell commands (cd then mkdir)
        parent_dir = str(target.parent.resolve())
        folder_name = target.name

        target.mkdir(parents=True, exist_ok=True)

        return f"Folder created: {target.name} at {target.resolve()}"
    except Exception as e:
        return f"Could not create folder: {e}"


def delete_file(path: str, name: str = "") -> str:
    try:
        base   = _resolve_path(path)
        target = (base / name) if name else base
        if not _is_safe_path(target):
            return f"Access denied: {target}"
        if not target.exists():
            return f"Not found: {target.name}"

        # Güvenli dizin kontrolü — kritik kullanıcı klasörlerini koru
        protected = {
            _get_desktop(), _get_downloads(), _get_documents(),
            _get_pictures(), _get_music(), _get_videos(), Path.home()
        }
        if target.resolve() in {p.resolve() for p in protected}:
            return f"Protected directory, cannot delete: {target.name}"

        return _safe_trash(target)

    except PermissionError:
        return f"Permission denied: {path}"
    except Exception as e:
        return f"Could not delete: {e}"


def move_file(path: str, name: str = "", destination: str = "") -> str:
    try:
        base   = _resolve_path(path)
        src    = (base / name) if name else base
        dst    = _resolve_path(destination) if destination else None

        if not src.exists():
            return f"Source not found: {src.name}"
        if dst is None:
            return "No destination specified."
        if not _is_safe_path(src):
            return f"Access denied (source): {src}"
        if not _is_safe_path(dst):
            return f"Access denied (destination): {dst}"

        if dst.is_dir():
            dst = dst / src.name

        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
        return f"Moved: {src.resolve()} → {dst.resolve()}"

    except Exception as e:
        return f"Could not move: {e}"


def copy_file(path: str, name: str = "", destination: str = "") -> str:
    try:
        base = _resolve_path(path)
        src  = (base / name) if name else base
        dst  = _resolve_path(destination) if destination else None

        if not src.exists():
            return f"Source not found: {src.name}"
        if dst is None:
            return "No destination specified."
        if not _is_safe_path(src):
            return f"Access denied (source): {src}"
        if not _is_safe_path(dst):
            return f"Access denied (destination): {dst}"

        if dst.is_dir():
            dst = dst / src.name

        dst.parent.mkdir(parents=True, exist_ok=True)

        if src.is_dir():
            shutil.copytree(str(src), str(dst))
        else:
            shutil.copy2(str(src), str(dst))

        return f"Copied: {src.resolve()} → {dst.resolve()}"

    except Exception as e:
        return f"Could not copy: {e}"


def rename_file(path: str, name: str = "", new_name: str = "") -> str:
    try:
        base     = _resolve_path(path)
        target   = (base / name) if name else base
        if not _is_safe_path(target):
            return f"Access denied: {target}"
        if not target.exists():
            return f"Not found: {target.name}"
        if not new_name:
            return "No new name provided."

        new_path = target.parent / new_name
        if new_path.exists():
            return f"A file named '{new_name}' already exists here."

        target.rename(new_path)
        return f"Renamed: {target.name} → {new_name} at {new_path.resolve()}"

    except Exception as e:
        return f"Could not rename: {e}"


def read_file(path: str, name: str = "", max_chars: int = 4000) -> str:
    try:
        base   = _resolve_path(path)
        target = (base / name) if name else base
        if not _is_safe_path(target):
            return f"Access denied: {target}"
        if not target.exists():
            return f"File not found: {target.name}"
        if not target.is_file():
            return f"Not a file: {target.name}"

        content = target.read_text(encoding="utf-8", errors="ignore")
        if len(content) > max_chars:
            content = content[:max_chars] + f"\n\n[Truncated — {len(content)} total chars]"
        return content

    except Exception as e:
        return f"Could not read file: {e}"


def write_file(path: str, name: str = "", content: str = "",
               append: bool = False) -> str:
    try:
        base   = _resolve_path(path)
        target = (base / name) if name else base
        if not _is_safe_path(target):
            return f"Access denied: {target}"
        target.parent.mkdir(parents=True, exist_ok=True)
        mode = "a" if append else "w"
        with open(target, mode, encoding="utf-8") as f:
            f.write(content)
        action = "Appended to" if append else "Written to"
        return f"{action}: {target.name} at {target.resolve()}"
    except Exception as e:
        return f"Could not write file: {e}"


def find_files(name: str = "", extension: str = "",
               path: str = "home", max_results: int = 20) -> str:
    try:
        search_path = _resolve_path(path)
        if not _is_safe_path(search_path):
            return f"Access denied: {search_path}"
        if not search_path.exists():
            return f"Search path not found: {path}"

        results    = []
        dir_count  = 0
        max_dirs   = 500  # performans + güvenlik limiti

        for item in search_path.rglob("*"):
            if item.is_dir():
                dir_count += 1
                if dir_count > max_dirs:
                    break
                continue
            if not item.is_file():
                continue
            if extension and item.suffix.lower() != extension.lower():
                continue
            if name and name.lower() not in item.name.lower():
                continue
            size = _format_size(item.stat().st_size)
            results.append(f"📄 {item.name} ({size}) — {item.parent}")
            if len(results) >= max_results:
                break

        if not results:
            query = name or extension or "files"
            return f"No {query} found in {search_path.name}/"

        return f"Found {len(results)} file(s):\n" + "\n".join(results)

    except Exception as e:
        return f"Search error: {e}"


def get_largest_files(path: str = "downloads", count: int = 10) -> str:
    count = min(count, 50)  # maksimum 50
    try:
        search_path = _resolve_path(path)
        if not _is_safe_path(search_path):
            return f"Access denied: {search_path}"
        if not search_path.exists():
            return f"Path not found: {path}"

        files = []
        for item in search_path.rglob("*"):
            if item.is_file():
                try:
                    files.append((item.stat().st_size, item))
                except Exception:
                    continue

        files.sort(reverse=True)
        top = files[:count]

        if not top:
            return "No files found."

        lines = [f"Top {len(top)} largest files in {search_path.name}/:"]
        for size, f in top:
            lines.append(f"  {_format_size(size):>10}  {f.name}  ({f.parent})")

        return "\n".join(lines)

    except Exception as e:
        return f"Error: {e}"


def get_disk_usage(path: str = "home") -> str:
    try:
        target = _resolve_path(path)
        usage  = shutil.disk_usage(target)
        pct    = usage.used / usage.total * 100
        return (
            f"Disk usage ({target}):\n"
            f"  Total : {_format_size(usage.total)}\n"
            f"  Used  : {_format_size(usage.used)} ({pct:.1f}%)\n"
            f"  Free  : {_format_size(usage.free)}"
        )
    except Exception as e:
        return f"Could not get disk usage: {e}"


def organize_desktop() -> str:
    type_map = {
        "Images":    {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".svg", ".ico", ".heic"},
        "Documents": {".pdf", ".doc", ".docx", ".txt", ".xls", ".xlsx",
                      ".ppt", ".pptx", ".csv", ".odt", ".ods", ".odp"},
        "Videos":    {".mp4", ".avi", ".mkv", ".mov", ".wmv", ".flv", ".webm", ".m4v"},
        "Music":     {".mp3", ".wav", ".flac", ".aac", ".ogg", ".wma", ".m4a"},
        "Archives":  {".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz"},
        "Code":      {".py", ".js", ".ts", ".html", ".css", ".json", ".xml",
                      ".cpp", ".java", ".cs", ".go", ".rs", ".sh"},
    }

    desktop = _get_desktop()
    moved, skipped = [], []

    try:
        for item in desktop.iterdir():
            # Klasörlere, gizli dosyalara ve organize klasörlerine dokunma
            if item.is_dir() or item.name.startswith("."):
                continue
            if item.name in {k for k in type_map}:
                continue

            ext        = item.suffix.lower()
            target_dir = desktop / "Others"
            for folder, exts in type_map.items():
                if ext in exts:
                    target_dir = desktop / folder
                    break

            target_dir.mkdir(exist_ok=True)
            new_path = target_dir / item.name

            if new_path.exists():
                skipped.append(item.name)
                continue

            shutil.move(str(item), str(new_path))
            moved.append(f"{item.name} → {target_dir.name}/")

        result = f"Desktop organized: {len(moved)} files moved."
        if moved:
            preview = moved[:8]
            result += "\n" + "\n".join(preview)
            if len(moved) > 8:
                result += f"\n... and {len(moved) - 8} more."
        if skipped:
            result += f"\n{len(skipped)} file(s) skipped (name conflict)."
        return result

    except Exception as e:
        return f"Could not organize desktop: {e}"


def open_folder(path: str, name: str = "") -> str:
    try:
        base   = _resolve_path(path)
        target = (base / name) if name else base
        if not _is_safe_path(target):
            return f"Access denied: {target}"
        if not target.exists():
            # Fallback: open browser search with the query
            query = f"{name or path}"
            encoded = urllib.parse.quote(query)
            search_url = f"https://www.google.com/search?q={encoded}"
            if _OS == "Windows":
                subprocess.Popen(["start", search_url])
            elif _OS == "Darwin":
                subprocess.Popen(["open", search_url])
            else:
                subprocess.Popen(["xdg-open", search_url])
            return f"I couldn't find '{query}' locally. I opened a web search for you instead."
        target_str = str(target)
        if _OS == "Windows":
            os.startfile(target_str)
        elif _OS == "Darwin":
            subprocess.Popen(["open", target_str], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            subprocess.Popen(["xdg-open", target_str], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return f"Opened: {target.name}"
    except Exception as e:
        return f"Could not open folder: {e}"


def get_file_info(path: str, name: str = "") -> str:
    try:
        base   = _resolve_path(path)
        target = (base / name) if name else base
        if not _is_safe_path(target):
            return f"Access denied: {target}"
        if not target.exists():
            return f"Not found: {target.name}"

        stat = target.stat()
        info = {
            "Name":      target.name,
            "Type":      "Folder" if target.is_dir() else "File",
            "Size":      _format_size(stat.st_size),
            "Location":  str(target.parent),
            "Created":   datetime.fromtimestamp(stat.st_ctime).strftime("%Y-%m-%d %H:%M"),
            "Modified":  datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
            "Extension": target.suffix or "—",
        }
        return "\n".join(f"  {k}: {v}" for k, v in info.items())

    except Exception as e:
        return f"Could not get file info: {e}"

def compress(path: str, name: str = "", archive_name: str = "", format: str = "zip") -> str:
    """Compress a file or folder into an archive."""
    try:
        base = _resolve_path(path)
        target = (base / name) if name else base
        if not _is_safe_path(target):
            return f"Access denied: {target}"
        if not target.exists():
            return f"Not found: {target.name}"

        if not archive_name:
            archive_name = target.name + f".{format}"
        elif not archive_name.endswith(f".{format}"):
            archive_name += f".{format}"

        archive_path = target.parent / archive_name

        if format == "zip":
            with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as zf:
                if target.is_file():
                    zf.write(target, target.name)
                else:
                    for item in target.rglob("*"):
                        if item.is_file():
                            zf.write(item, item.relative_to(target.parent))
        elif format in ("tar", "tar.gz", "tgz", "tar.bz2", "tbz2"):
            mode = format if format in ("tar", "tar.gz", "tar.bz2") else {
                "tgz": "tar.gz", "tbz2": "tar.bz2"
            }.get(format, "tar.gz")
            with tarfile.open(archive_path, f"w:{mode.split('tar.').pop() if 'tar.' in mode else ''}" or "w") as tf:
                tf.add(target, target.name)
        else:
            return f"Unsupported format: {format}. Use zip, tar, tar.gz, tgz, tar.bz2"

        size = _format_size(archive_path.stat().st_size)
        return f"Compressed to {archive_name} ({size}) at {archive_path.resolve()}"
    except Exception as e:
        return f"Compression failed: {e}"


def extract(path: str, name: str = "", destination: str = "") -> str:
    """Extract an archive file."""
    try:
        base = _resolve_path(path)
        target = (base / name) if name else base
        if not _is_safe_path(target):
            return f"Access denied: {target}"
        if not target.exists():
            return f"Archive not found: {target.name}"

        dst = _resolve_path(destination) if destination else target.parent / target.stem
        dst.mkdir(parents=True, exist_ok=True)

        suffix = target.suffix.lower()
        if suffix == ".zip" or target.name.endswith(".zip"):
            with zipfile.ZipFile(target, "r") as zf:
                zf.extractall(dst)
        elif suffix in (".tar", ".gz", ".bz2", ".xz") or "".join(target.suffixes[-2:]) in (".tar.gz", ".tar.bz2", ".tar.xz"):
            with tarfile.open(target, "r:*") as tf:
                tf.extractall(dst)
        else:
            return f"Unsupported archive format: {suffix}"

        count = sum(1 for _ in dst.rglob("*"))
        return f"Extracted {count} items to {dst.resolve()}"
    except Exception as e:
        return f"Extraction failed: {e}"


def download(url: str, destination: str = "downloads", filename: str = "") -> str:
    """Download a file from a URL."""
    try:
        import requests
        dst_dir = _resolve_path(destination)
        dst_dir.mkdir(parents=True, exist_ok=True)

        if not _is_safe_path(dst_dir):
            return f"Access denied: {dst_dir}"

        # Get filename from URL if not specified
        if not filename:
            filename = url.rstrip("/").split("/")[-1]
            if not filename or "." not in filename:
                filename = "downloaded_file"

        filepath = dst_dir / filename

        response = requests.get(url, stream=True, timeout=30)
        response.raise_for_status()

        # Try to get better filename from Content-Disposition
        content_disp = response.headers.get("content-disposition", "")
        if "filename=" in content_disp:
            import re
            match = re.search(r'filename=["\']?([^"\'\n]+)', content_disp)
            if match:
                filepath = dst_dir / match.group(1).strip()

        with open(filepath, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

        size = _format_size(filepath.stat().st_size)
        return f"Downloaded {filepath.name} ({size}) to {filepath.resolve()}"
    except ImportError:
        return "requests module required for download. Run: pip install requests"
    except Exception as e:
        return f"Download failed: {e}"


def edit_file(path: str, name: str = "", old_string: str = "", new_string: str = "", replace_all: bool = False) -> str:
    """Edit a file by replacing text. Used for self-improvement - Jarvis can modify its own code."""
    try:
        base = _resolve_path(path)
        target = (base / name) if name else base
        if not _is_safe_path(target):
            return f"Access denied: {target}"
        if not target.exists():
            return f"File not found: {target.name}"
        if not target.is_file():
            return f"Not a file: {target.name}"
        if not old_string:
            return "No old_string provided for replacement."

        content = target.read_text(encoding="utf-8", errors="replace")

        if replace_all:
            count = content.count(old_string)
            if count == 0:
                return f"String not found in {target.name}"
            content = content.replace(old_string, new_string)
        else:
            if old_string not in content:
                return f"String not found in {target.name}"
            content = content.replace(old_string, new_string, 1)
            count = 1

        target.write_text(content, encoding="utf-8")
        return f"Edited {target.name} at {target.resolve()}: {count} replacement(s) made."
    except PermissionError:
        return f"Permission denied: {target}"
    except Exception as e:
        return f"Edit failed: {e}"


def file_controller(
    parameters: dict = None,
    response=None,
    player=None,
    session_memory=None,
) -> str:
    params = parameters or {}
    action = params.get("action", "").lower().strip()
    path   = params.get("path", "home")
    name   = params.get("name", "")

    if player:
        player.write_log(f"[file] {action} {name or path}")

    try:
        if action == "list":
            return list_files(path)

        elif action == "create_file":
            return create_file(path, name=name, content=params.get("content", ""))

        elif action == "create_folder":
            return create_folder(path, name=name)

        elif action == "delete":
            return delete_file(path, name=name)

        elif action == "move":
            return move_file(path, name=name, destination=params.get("destination", ""))

        elif action == "copy":
            return copy_file(path, name=name, destination=params.get("destination", ""))

        elif action == "rename":
            return rename_file(path, name=name, new_name=params.get("new_name", ""))

        elif action == "read":
            return read_file(path, name=name)

        elif action == "write":
            return write_file(
                path, name=name,
                content=params.get("content", ""),
                append=params.get("append", False)
            )

        elif action == "find":
            return find_files(
                name=name or params.get("name", ""),
                extension=params.get("extension", ""),
                path=path,
                max_results=min(int(params.get("max_results", 20)), 50),
            )

        elif action == "largest":
            return get_largest_files(
                path=path,
                count=int(params.get("count", 10)),
            )

        elif action == "disk_usage":
            return get_disk_usage(path)

        elif action == "organize_desktop":
            return organize_desktop()

        elif action in ("open_folder", "open", "reveal", "show"):
            return open_folder(path, name=name)

        elif action == "info":
            return get_file_info(path, name=name)

        elif action in ("compress", "zip", "archive"):
            return compress(
                path, name=name,
                archive_name=params.get("archive_name", ""),
                format=params.get("format", "zip"),
            )

        elif action in ("extract", "unzip", "unpack"):
            return extract(
                path, name=name,
                destination=params.get("destination", ""),
            )

        elif action == "download":
            return download(
                url=params.get("url", ""),
                destination=path,
                filename=params.get("file_name", ""),
            )

        elif action in ("edit", "edit_file", "replace"):
            return edit_file(
                path, name=name,
                old_string=params.get("old_string", ""),
                new_string=params.get("new_string", ""),
                replace_all=params.get("replace_all", False),
            )

        else:
            return f"Unknown action: '{action}'"

    except Exception as e:
        return f"File controller error ({action}): {e}"