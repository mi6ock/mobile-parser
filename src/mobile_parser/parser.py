# coding: utf-8
"""OmniParser core - simplified image parsing for macOS."""

import os
import sys
import io
import base64
import time
from typing import Dict, List, Optional, Tuple, Union

import cv2
import numpy as np
import torch
from PIL import Image
from torchvision.ops import box_convert
from torchvision.transforms import ToPILImage
import supervision as sv

# Suppress unnecessary output
import warnings
warnings.filterwarnings("ignore")


def get_device() -> str:
    """Select the best available device for inference."""
    if torch.cuda.is_available():
        return "cuda"
    elif torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def get_dtype(device: str) -> torch.dtype:
    """Get appropriate dtype for the device."""
    # MPS and CPU work better with float32
    if device == "cuda":
        return torch.float16
    return torch.float32


INPUT_IMAGE_MAX_SIZE = 960
ANNOTATED_IMAGE_MAX_SIZE = 1568  # Claude optimal processing size (long edge)


class OmniParserSimple:
    """Simplified OmniParser for image parsing only."""

    def __init__(self, weights_dir: Optional[str] = None, device: Optional[str] = None):
        """Initialize OmniParser.

        Args:
            weights_dir: Directory containing model weights. If None, will download from HuggingFace.
            device: Device to use (cuda/mps/cpu). If None, auto-detect.
        """
        self.device = device or get_device()
        self.dtype = get_dtype(self.device)
        self.weights_dir = weights_dir

        # Lazy loading - models loaded on first use
        self._yolo_model = None
        self._caption_model = None
        self._caption_processor = None
        self._ocr_reader = None

        print(f"OmniParser initialized (device={self.device}, dtype={self.dtype})", file=sys.stderr)

    @staticmethod
    def _resize_for_parsing(image: Image.Image, max_size: int = INPUT_IMAGE_MAX_SIZE) -> Tuple[Image.Image, float]:
        """Resize image for faster parsing, return resized image and scale factor."""
        width, height = image.size
        if width <= max_size and height <= max_size:
            return image, 1.0

        if width >= height:
            new_width = max_size
            new_height = int(max_size * height / width)
        else:
            new_height = max_size
            new_width = int(max_size * width / height)

        scale = width / new_width  # scale factor to map back to original coords
        resized = image.resize((new_width, new_height), Image.LANCZOS)
        return resized, scale

    def _ensure_weights(self) -> str:
        """Ensure model weights are available, downloading if necessary."""
        if self.weights_dir and os.path.exists(self.weights_dir):
            return self.weights_dir

        # Download from HuggingFace Hub
        from huggingface_hub import snapshot_download

        cache_dir = os.path.join(os.path.expanduser("~"), ".cache", "omniparser")
        os.makedirs(cache_dir, exist_ok=True)

        print("Downloading OmniParser models from HuggingFace...", file=sys.stderr)
        weights_dir = snapshot_download(
            repo_id="microsoft/OmniParser-v2.0",
            local_dir=cache_dir,
            local_dir_use_symlinks=False
        )

        self.weights_dir = weights_dir
        return weights_dir

    @property
    def yolo_model(self):
        """Lazy load YOLO model."""
        if self._yolo_model is None:
            from ultralytics import YOLO

            weights_dir = self._ensure_weights()
            model_path = os.path.join(weights_dir, "icon_detect", "model.pt")

            if not os.path.exists(model_path):
                # Try alternative path structure
                model_path = os.path.join(weights_dir, "icon_detect", "model.pt")

            print(f"Loading YOLO model from {model_path}...", file=sys.stderr)
            self._yolo_model = YOLO(model_path)
            self._yolo_model.to(self.device)

        return self._yolo_model

    @property
    def caption_model_processor(self):
        """Lazy load caption model (Florence-2)."""
        if self._caption_model is None:
            from transformers import AutoProcessor, AutoModelForCausalLM

            weights_dir = self._ensure_weights()
            # Try fine-tuned model paths (name varies by OmniParser version)
            model_path = None
            for subdir in ["icon_caption_florence", "icon_caption"]:
                candidate = os.path.join(weights_dir, subdir)
                if os.path.exists(candidate):
                    model_path = candidate
                    break
            if model_path is None:
                model_path = "microsoft/Florence-2-base"

            print(f"Loading Florence-2 model from {model_path}...", file=sys.stderr)

            # Processor needs the base model (icon_caption dir has no tokenizer files)
            self._caption_processor = AutoProcessor.from_pretrained(
                "microsoft/Florence-2-base-ft",
                trust_remote_code=True
            )

            if self.device == "cuda":
                self._caption_model = AutoModelForCausalLM.from_pretrained(
                    model_path,
                    torch_dtype=torch.float16,
                    trust_remote_code=True
                ).to(self.device)
            else:
                self._caption_model = AutoModelForCausalLM.from_pretrained(
                    model_path,
                    torch_dtype=torch.float32,
                    trust_remote_code=True
                ).to(self.device)

        return {"model": self._caption_model, "processor": self._caption_processor}

    @property
    def ocr_reader(self):
        """Lazy load EasyOCR reader."""
        if self._ocr_reader is None:
            import easyocr
            print("Loading EasyOCR...", file=sys.stderr)
            self._ocr_reader = easyocr.Reader(['en', 'ja'], gpu=(self.device == "cuda"))
        return self._ocr_reader

    def parse_image(self, image: Union[str, Image.Image], box_threshold: float = 0.05) -> Dict:
        """Parse an image and extract UI elements.

        Args:
            image: Path to image file or PIL Image object
            box_threshold: Confidence threshold for detection

        Returns:
            Dictionary with elements and image info
        """
        # Load image
        if isinstance(image, str):
            image = Image.open(image)

        if image.mode != "RGB":
            image = image.convert("RGB")

        orig_width, orig_height = image.size

        # Resize for faster parsing
        resized, scale = self._resize_for_parsing(image)
        rw, rh = resized.size
        print(f"Image: {orig_width}x{orig_height} -> {rw}x{rh} (scale={scale:.2f})", file=sys.stderr)

        # Run OCR on resized image
        ocr_text, ocr_bbox = self._run_ocr(resized)

        # Run YOLO detection on resized image
        yolo_boxes = self._run_yolo(resized, box_threshold)

        # Merge and deduplicate (using resized dimensions)
        elements = self._merge_detections(
            resized, rw, rh,
            ocr_text, ocr_bbox,
            yolo_boxes
        )

        # Scale coordinates back to original image size
        if scale != 1.0:
            for elem in elements:
                elem["bbox_pixel"] = [int(v * scale) for v in elem["bbox_pixel"]]
                elem["center_x"] = int(elem["center_x"] * scale)
                elem["center_y"] = int(elem["center_y"] * scale)

        # Generate annotated image using original image with scaled-back coords
        annotated_image_b64 = self._annotate_image(image, elements)

        return {
            "elements": elements,
            "image_size": {"width": orig_width, "height": orig_height},
            "annotated_image": annotated_image_b64
        }

    def parse_base64(self, image_base64: str, box_threshold: float = 0.05) -> Dict:
        """Parse a base64-encoded image.

        Args:
            image_base64: Base64-encoded image data
            box_threshold: Confidence threshold for detection

        Returns:
            Dictionary with elements and image info
        """
        image_bytes = base64.b64decode(image_base64)
        image = Image.open(io.BytesIO(image_bytes))
        return self.parse_image(image, box_threshold)

    def _run_ocr(self, image: Image.Image) -> Tuple[List[str], List[List[int]]]:
        """Run OCR on image."""
        image_np = np.array(image)

        result = self.ocr_reader.readtext(image_np, text_threshold=0.8)

        texts = []
        bboxes = []

        for item in result:
            coord = item[0]
            text = item[1]

            # Convert polygon to xyxy
            x1 = int(min(p[0] for p in coord))
            y1 = int(min(p[1] for p in coord))
            x2 = int(max(p[0] for p in coord))
            y2 = int(max(p[1] for p in coord))

            texts.append(text)
            bboxes.append([x1, y1, x2, y2])

        return texts, bboxes

    def _run_yolo(self, image: Image.Image, box_threshold: float) -> List[List[float]]:
        """Run YOLO detection on image."""
        result = self.yolo_model.predict(
            source=image,
            conf=box_threshold,
            iou=0.7,
            verbose=False
        )

        boxes = result[0].boxes.xyxy.cpu().tolist()
        return boxes

    def _merge_detections(
        self,
        image: Image.Image,
        width: int,
        height: int,
        ocr_texts: List[str],
        ocr_bboxes: List[List[int]],
        yolo_boxes: List[List[float]]
    ) -> List[Dict]:
        """Merge OCR and YOLO detections, removing overlaps."""
        elements = []

        # Add OCR elements first (text takes priority)
        for i, (text, bbox) in enumerate(zip(ocr_texts, ocr_bboxes)):
            x1, y1, x2, y2 = bbox
            elements.append({
                "id": len(elements),
                "type": "text",
                "content": text,
                "bbox": [x1/width, y1/height, x2/width, y2/height],  # Normalized
                "bbox_pixel": [x1, y1, x2, y2],
                "center_x": (x1 + x2) // 2,
                "center_y": (y1 + y2) // 2
            })

        # Add YOLO boxes that don't overlap with OCR
        ocr_boxes_normalized = [[b[0]/width, b[1]/height, b[2]/width, b[3]/height] for b in ocr_bboxes]

        # Collect non-overlapping icon boxes for batch captioning
        icon_boxes = []
        for yolo_box in yolo_boxes:
            x1, y1, x2, y2 = yolo_box
            box_normalized = [x1/width, y1/height, x2/width, y2/height]
            if not self._has_significant_overlap(box_normalized, ocr_boxes_normalized):
                icon_boxes.append((box_normalized, [int(x1), int(y1), int(x2), int(y2)]))

        # Batch caption all icons at once
        if icon_boxes:
            pixel_boxes = [b[1] for b in icon_boxes]
            captions = self._get_icon_captions_batch(image, pixel_boxes)
        else:
            captions = []

        for (box_normalized, pixel_box), caption in zip(icon_boxes, captions):
            x1, y1, x2, y2 = pixel_box
            elements.append({
                "id": len(elements),
                "type": "icon",
                "content": caption,
                "bbox": box_normalized,
                "bbox_pixel": pixel_box,
                "center_x": int((x1 + x2) / 2),
                "center_y": int((y1 + y2) / 2)
            })

        return elements

    def _has_significant_overlap(self, box: List[float], other_boxes: List[List[float]], threshold: float = 0.7) -> bool:
        """Check if box has significant overlap with any other box."""
        def iou(box1, box2):
            x1 = max(box1[0], box2[0])
            y1 = max(box1[1], box2[1])
            x2 = min(box1[2], box2[2])
            y2 = min(box1[3], box2[3])

            intersection = max(0, x2 - x1) * max(0, y2 - y1)
            area1 = (box1[2] - box1[0]) * (box1[3] - box1[1])
            area2 = (box2[2] - box2[0]) * (box2[3] - box2[1])
            union = area1 + area2 - intersection

            if union == 0:
                return 0
            return intersection / union

        for other_box in other_boxes:
            if iou(box, other_box) > threshold:
                return True
        return False

    @torch.inference_mode()
    def _get_icon_captions_batch(self, image: Image.Image, bboxes: List[List[int]], batch_size: int = 128) -> List[str]:
        """Get captions for multiple icon regions in batch."""
        if not bboxes:
            return []

        try:
            # Crop and resize all icons
            cropped_images = []
            for bbox in bboxes:
                x1, y1, x2, y2 = bbox
                cropped = image.crop((x1, y1, x2, y2))
                cropped = cropped.resize((64, 64))
                cropped_images.append(cropped)

            model = self.caption_model_processor["model"]
            processor = self.caption_model_processor["processor"]
            prompt = "<CAPTION>"

            captions = []
            for i in range(0, len(cropped_images), batch_size):
                batch = cropped_images[i:i + batch_size]

                if model.device.type == "cuda":
                    inputs = processor(
                        images=batch,
                        text=[prompt] * len(batch),
                        return_tensors="pt",
                        do_resize=False
                    ).to(device=model.device, dtype=torch.float16)
                else:
                    inputs = processor(
                        images=batch,
                        text=[prompt] * len(batch),
                        return_tensors="pt",
                        do_resize=False
                    ).to(device=model.device)

                generated_ids = model.generate(
                    input_ids=inputs["input_ids"],
                    pixel_values=inputs["pixel_values"],
                    max_new_tokens=20,
                    num_beams=1,
                    do_sample=False
                )

                texts = processor.batch_decode(generated_ids, skip_special_tokens=True)
                captions.extend([t.strip() if t.strip() else "icon" for t in texts])

            return captions

        except Exception as e:
            print(f"Batch caption generation failed: {e}", file=sys.stderr)
            return ["icon"] * len(bboxes)

    def _annotate_image(self, image: Image.Image, elements: List[Dict]) -> str:
        """Create annotated image with bounding boxes and IDs."""
        image_np = np.array(image)

        # Draw boxes and labels
        for elem in elements:
            bbox = elem["bbox_pixel"]
            x1, y1, x2, y2 = bbox
            elem_id = elem["id"]
            elem_type = elem["type"]

            # Color based on type
            color = (0, 255, 0) if elem_type == "text" else (255, 0, 0)

            # Draw rectangle
            cv2.rectangle(image_np, (x1, y1), (x2, y2), color, 2)

            # Draw ID label
            label = str(elem_id)
            font = cv2.FONT_HERSHEY_SIMPLEX
            font_scale = 0.6
            thickness = 2

            (text_width, text_height), baseline = cv2.getTextSize(label, font, font_scale, thickness)

            # Background for label
            cv2.rectangle(
                image_np,
                (x1, y1 - text_height - 4),
                (x1 + text_width + 4, y1),
                color,
                -1
            )

            # Label text
            cv2.putText(
                image_np,
                label,
                (x1 + 2, y1 - 2),
                font,
                font_scale,
                (255, 255, 255),
                thickness
            )

        # Encode to base64
        pil_img = Image.fromarray(image_np)

        # Resize: fit long edge to ANNOTATED_IMAGE_MAX_SIZE
        w, h = pil_img.size
        if max(w, h) > ANNOTATED_IMAGE_MAX_SIZE:
            if w >= h:
                new_w = ANNOTATED_IMAGE_MAX_SIZE
                new_h = int(ANNOTATED_IMAGE_MAX_SIZE * h / w)
            else:
                new_h = ANNOTATED_IMAGE_MAX_SIZE
                new_w = int(ANNOTATED_IMAGE_MAX_SIZE * w / h)
            pil_img = pil_img.resize((new_w, new_h), Image.LANCZOS)

        buffered = io.BytesIO()
        pil_img.save(buffered, format="PNG")
        return base64.b64encode(buffered.getvalue()).decode("ascii")


# Global parser instance (lazy initialized)
_parser: Optional[OmniParserSimple] = None


def get_parser() -> OmniParserSimple:
    """Get or create the global parser instance."""
    global _parser
    if _parser is None:
        # Check for environment variable for weights directory
        weights_dir = os.environ.get("OMNIPARSER_WEIGHTS_DIR")
        device = os.environ.get("OMNIPARSER_DEVICE")
        _parser = OmniParserSimple(weights_dir=weights_dir, device=device)
    return _parser
