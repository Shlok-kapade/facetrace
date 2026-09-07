"""Stage 1: Face Detection & Encoding using face_recognition (dlib-based)."""

import os
from dataclasses import dataclass

import face_recognition
from PIL import Image
import numpy as np


@dataclass
class FaceResult:
    """Result from face detection stage."""
    face_crop_path: str
    encoding: list  # 128-d face encoding
    bbox: tuple     # top, right, bottom, left
    num_faces_detected: int


def detect_and_encode(image_path: str, output_dir: str = ".") -> FaceResult:
    """
    Load image, detect face(s), crop the largest face, save crop, return encoding.

    Args:
        image_path: Path to input image.
        output_dir: Directory to save the cropped face image.

    Returns:
        FaceResult with crop path, encoding, bounding box, and face count.

    Raises:
        FileNotFoundError: If image_path does not exist.
        ValueError: If no face is detected in the image.
    """
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"Image not found: {image_path}")

    print(f"  Loading image: {image_path}")
    image = face_recognition.load_image_file(image_path)

    # Detect all face locations (top, right, bottom, left)
    face_locations = face_recognition.face_locations(image, model="hog")
    num_faces = len(face_locations)
    print(f"  Detected {num_faces} face(s)")

    if num_faces == 0:
        raise ValueError(
            "No face detected in the image. Please provide a clear photo with a visible face."
        )

    # Pick the largest face by bounding box area
    if num_faces > 1:
        print(f"  Multiple faces found -- selecting largest bounding box")

    def bbox_area(loc):
        top, right, bottom, left = loc
        return (bottom - top) * (right - left)

    best_loc = max(face_locations, key=bbox_area)
    top, right, bottom, left = best_loc

    # Generate 128-d encoding for the selected face
    encodings = face_recognition.face_encodings(image, known_face_locations=[best_loc])
    if not encodings:
        raise ValueError("Could not generate face encoding -- face may be too small or obscured.")
    encoding = encodings[0].tolist()

    # Crop face with some padding
    h, w = image.shape[:2]
    pad_y = int((bottom - top) * 0.3)
    pad_x = int((right - left) * 0.3)
    crop_top = max(0, top - pad_y)
    crop_bottom = min(h, bottom + pad_y)
    crop_left = max(0, left - pad_x)
    crop_right = min(w, right + pad_x)

    face_crop = image[crop_top:crop_bottom, crop_left:crop_right]

    # Save cropped face
    crop_path = os.path.join(output_dir, "face_crop.jpg")
    pil_img = Image.fromarray(face_crop)
    pil_img.save(crop_path, quality=95)
    print(f"  Saved cropped face to: {crop_path}")
    print(f"  Face encoding: 128-d vector (first 5 values: {encoding[:5]}...)")

    return FaceResult(
        face_crop_path=crop_path,
        encoding=encoding,
        bbox=(top, right, bottom, left),
        num_faces_detected=num_faces,
    )
