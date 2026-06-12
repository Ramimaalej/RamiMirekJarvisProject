import os
import shutil
from pathlib import Path


def reset_hf_offline_flags() -> None:
    """Clear the HF offline env vars and the cached Hugging Face constants.

    The Hugging Face client caches the offline state at import time, so
    simply doing os.environ.pop(...) is not enough after the first failed
    download attempt. We must also force the cached constants to False before
    retrying a model download.
    """
    os.environ.pop("HF_HUB_OFFLINE", None)
    os.environ.pop("TRANSFORMERS_OFFLINE", None)
    os.environ.pop("HF_DATASETS_OFFLINE", None)

    # Some libraries cache this value in module constants when imported.
    try:
        import huggingface_hub.constants as hf_constants

        hf_constants.HF_HUB_OFFLINE = False
    except Exception:
        pass

    try:
        import transformers.utils.hub as transformers_hub

        if hasattr(transformers_hub, "constants"):
            transformers_hub.constants.HF_HUB_OFFLINE = False
    except Exception:
        pass


def remove_broken_hf_snapshot(model_name: str) -> list[str]:
    """Delete broken Hugging Face cache folders for a model name.

    Returns the list of deleted snapshot folders.
    """
    removed: list[str] = []
    cache_dir = Path.home() / ".cache" / "huggingface" / "hub"
    if not cache_dir.exists():
        return removed

    # Match common patterns such as models--Systran--faster-whisper-base.
    prefix = f"models--*--{model_name}"
    for candidate in cache_dir.glob(prefix):
        if candidate.is_dir():
            shutil.rmtree(candidate, ignore_errors=True)
            removed.append(str(candidate))
    return removed
