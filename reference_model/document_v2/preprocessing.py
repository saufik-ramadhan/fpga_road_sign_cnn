"""Pillow-only document-v2 preprocessing shared by training and board clients."""
from PIL import Image, ImageOps


def preprocess_image(image, roi=None, size=16):
    """Return prepared L pixels; ROI maxima are inclusive in decoded coordinates.

    No EXIF rotation is applied, matching the training dataset's coordinates.
    Without ROI the caller supplies an already cropped traffic-sign image.
    """
    if roi is None:
        roi = (0, 0, image.width - 1, image.height - 1)
    if len(roi) != 4 or any(type(v) is not int for v in roi):
        raise ValueError('ROI must contain four integer coordinates')
    x1, y1, x2, y2 = roi
    if not (0 <= x1 < x2 < image.width and 0 <= y1 < y2 < image.height):
        raise ValueError('ROI outside image or smaller than 2 x 2 pixels')
    crop = image.convert('RGB').crop((x1, y1, x2 + 1, y2 + 1)).convert('L')
    return ImageOps.equalize(crop).resize((size, size), Image.Resampling.BILINEAR)
