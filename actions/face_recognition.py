import logging
import os
import platform
import tempfile
from pathlib import Path
from typing import Any

import cv2
import numpy as np

logger = logging.getLogger("face_recognition")

_OS = platform.system()
_CASCADE_DIR = Path(cv2.data.haarcascades) if hasattr(cv2, "data") else Path(cv2.__file__).parent / "data"


def _get_cascade(name: str = "haarcascade_frontalface_default.xml") -> cv2.CascadeClassifier | None:
    path = _CASCADE_DIR / name
    if path.exists():
        return cv2.CascadeClassifier(str(path))
    alt = Path(cv2.__file__).parent.parent / "share" / "opencv4" / "haarcascades" / name
    if alt.exists():
        return cv2.CascadeClassifier(str(alt))
    logger.warning("Haar cascade not found: %s", name)
    return None


def detect_faces(image: np.ndarray) -> list[dict[str, Any]]:
    cascade = _get_cascade()
    if cascade is None:
        return []
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    faces = cascade.detectMultiScale(
        gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30),
    )
    results = []
    for (x, y, w, h) in faces:
        results.append({
            "x": int(x), "y": int(y), "width": int(w), "height": int(h),
            "confidence": 0.0,
        })
    return results


def detect_smiles(image: np.ndarray) -> list[dict[str, Any]]:
    cascade = _get_cascade("haarcascade_smile.xml")
    if cascade is None:
        return []
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    smiles = cascade.detectMultiScale(
        gray, scaleFactor=1.8, minNeighbors=20, minSize=(25, 25),
    )
    return [
        {"x": int(x), "y": int(y), "width": int(w), "height": int(h)}
        for (x, y, w, h) in smiles
    ]


def detect_eyes(image: np.ndarray) -> list[dict[str, Any]]:
    cascade = _get_cascade("haarcascade_eye.xml")
    if cascade is None:
        return []
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    eyes = cascade.detectMultiScale(
        gray, scaleFactor=1.1, minNeighbors=5, minSize=(20, 20),
    )
    return [
        {"x": int(x), "y": int(y), "width": int(w), "height": int(h)}
        for (x, y, w, h) in eyes
    ]


def capture_camera(index: int = 0) -> np.ndarray | None:
    backend = cv2.CAP_ANY
    if _OS == "Windows":
        backend = cv2.CAP_DSHOW
    elif _OS == "Darwin":
        backend = cv2.CAP_AVFOUNDATION
    cap = cv2.VideoCapture(index, backend)
    if not cap.isOpened():
        for i in range(3):
            cap = cv2.VideoCapture(i, backend)
            if cap.isOpened():
                break
        else:
            return None
    ret, frame = cap.read()
    cap.release()
    return frame if ret else None


def analyze_camera_feed(detect: str = "faces") -> dict[str, Any]:
    frame = capture_camera()
    if frame is None:
        return {"error": "No camera available", "faces": 0}

    result = {"faces": 0, "people": [], "expressions": {}}

    faces = detect_faces(frame)
    result["faces"] = len(faces)
    result["people"] = faces

    if faces:
        smiles = detect_smiles(frame)
        result["expressions"]["smiling"] = len(smiles) > 0

        eyes = detect_eyes(frame)
        result["expressions"]["eyes_detected"] = len(eyes)

    return result
