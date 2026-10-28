import asyncio
import re

import numpy as np
from winrt.windows.graphics.imaging import BitmapPixelFormat, SoftwareBitmap
from winrt.windows.media.ocr import OcrEngine
from winrt.windows.storage.streams import DataWriter


class WinOcr:
    """Windows' built-in OCR behind the same read_lines() the engine expects from Tesseract."""

    def __init__(self):
        self.engine = OcrEngine.try_create_from_user_profile_languages()
        if self.engine is None:
            raise RuntimeError("Windows OCR niedostepny")
        self._version = "Windows.Media.Ocr"

    def version(self):
        return self._version

    def _bitmap(self, gray):
        h, w = gray.shape
        bgra = np.dstack([gray, gray, gray, np.full_like(gray, 255)]).astype(np.uint8)
        writer = DataWriter()
        writer.write_bytes(bgra.tobytes())
        bmp = SoftwareBitmap(BitmapPixelFormat.BGRA8, w, h)
        bmp.copy_from_buffer(writer.detach_buffer())
        return bmp

    async def _read(self, images):
        out = []
        for img in images:
            img = np.asarray(img)
            if img.ndim == 3:
                img = img.mean(axis=2)
            res = await self.engine.recognize_async(self._bitmap(np.clip(img, 0, 255).astype(np.uint8)))
            out.append(" ".join(line.text for line in res.lines))
        return out

    def read_lines(self, images, chars=None):
        texts = [re.sub(r"(?<![A-Za-z])[lI](st|nd|rd|th)\b", r"1\1", t) for t in asyncio.run(self._read(images))]
        if chars:
            texts = ["".join(c for c in t if c in chars) for t in texts]
        return texts

    def read_line(self, image, chars=None):
        return self.read_lines([image], chars)[0]
