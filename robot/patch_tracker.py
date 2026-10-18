"""Find the sticker on the wearer's pants (target.png) in a camera frame.

Two steps, so it's both fast and hard to fool:
  1. Colour: the sticker is bright green with a light outline on dark pants. Find blobs of
     "green or light", roughly the sticker's shape (taller than wide).
  2. Pattern: compare each candidate with the reference picture (normalised correlation), at the
     candidate's size. Keep the best one if it scores well enough.

find(frame) -> dict(cx=-1..1 left/right, size=0..1 height as share of frame, score=0..1, box) or None.
Settings: PATCH_* in follow_config.py.
"""
import cv2
import numpy as np

import follow_config as cfg


class PatchTracker:
    def __init__(self, image_path):
        ref = cv2.imread(image_path)
        if ref is None:
            raise FileNotFoundError(f"sticker reference not found: {image_path}")
        self.ref_grey = cv2.cvtColor(ref, cv2.COLOR_BGR2GRAY)
        h, w = self.ref_grey.shape
        self.ref_aspect = w / h                      # ~0.73: taller than wide
        self.kernel = np.ones((5, 5), np.uint8)

    def _mask(self, hsv):
        green = cv2.inRange(hsv, cfg.PATCH_GREEN_LO, cfg.PATCH_GREEN_HI)
        light = cv2.inRange(hsv, cfg.PATCH_LIGHT_LO, cfg.PATCH_LIGHT_HI)
        return cv2.morphologyEx(cv2.bitwise_or(green, light), cv2.MORPH_CLOSE, self.kernel)

    def find(self, frame):
        fh, fw = frame.shape[:2]
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        grey = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        n, _, stats, _ = cv2.connectedComponentsWithStats(self._mask(hsv))
        best = None
        for i in range(1, n):
            x, y, w, h, area = stats[i]
            if h < cfg.PATCH_MIN_PX or h > 0.9 * fh:
                continue
            if abs(w / h - self.ref_aspect) > cfg.PATCH_ASPECT_TOL:
                continue
            if area < 0.2 * w * h:                     # outline + green fill; up close mostly the outline
                continue
            # Pattern check at this candidate's size
            patch = grey[y:y + h, x:x + w]
            ref = cv2.resize(self.ref_grey, (w, h), interpolation=cv2.INTER_AREA)
            score = float(cv2.matchTemplate(patch, ref, cv2.TM_CCOEFF_NORMED)[0, 0])
            if score >= cfg.PATCH_MIN_SCORE and (best is None or score > best["score"]):
                best = dict(cx=((x + w / 2) - fw / 2) / (fw / 2), size=h / fh, score=score,
                            box=(int(x), int(y), int(x + w), int(y + h)))
        return best

    @staticmethod
    def draw(frame, hit):
        if hit:
            x1, y1, x2, y2 = hit["box"]
            cv2.rectangle(frame, (x1, y1), (x2, y2), (255, 0, 255), 3)
            cv2.putText(frame, f"STICKER {hit['score']:.2f}", (x1, max(14, y1 - 8)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 0, 255), 2)
