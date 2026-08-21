from PIL import Image, ImageOps
import logging
import os

logger = logging.getLogger(__name__)

def edit_image(parameters: dict | None = None, player=None) -> str:
    parameters = parameters or {}
    path = (parameters.get("path") or "").strip()
    action = (parameters.get("action") or "resize").lower()
    
    if not path or not os.path.exists(path):
        return "Image file not found."
        
    try:
        with Image.open(path) as img:
            out_path = f"edited_{os.path.basename(path)}"
            if action == "grayscale":
                img = ImageOps.grayscale(img)
            elif action == "flip":
                img = ImageOps.flip(img)
            elif action == "mirror":
                img = ImageOps.mirror(img)
            elif action == "resize":
                w = int(parameters.get("width") or 800)
                h = int(parameters.get("height") or 600)
                img = img.resize((w, h))
            
            img.save(out_path)
            return f"Image edited ({action}) and saved as {out_path}"
    except Exception as e:
        return f"Image editing failed: {e}"
