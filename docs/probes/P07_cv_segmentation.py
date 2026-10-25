"""P07 - User-proposed classical CV segmentation of screenshots, tested for robustness.
Pipeline (from the user's Krita experiment): grayscale -> (auto-invert if dark theme)
-> contrast curve -> threshold -> edge detection -> rectangles (panels) -> OCR per panel.
Run on every PNG plus synthetic variants (0.6x, 1.5x, inverted) and report whether
the same panels are found (normalised to image size).
Run from repo root: python docs/probes/P07_cv_segmentation.py
"""
import glob, os
import cv2, numpy as np

def prep(img):
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    if g.mean() < 128: g = 255 - g                                   # dark theme -> light
    # contrast curve similar to the Krita S-curve: gamma > 1 darkens mid/low tones
    g = np.clip(255 * (g / 255.0) ** 2.2, 0, 255).astype(np.uint8)
    return g

def panels(img, thr=None):
    """v2: theme-aware ink threshold relative to the page background (the user's
    'threshold at 210' generalised), then long-line morphology (scale-relative kernels)
    to keep only panel/row borders, then rectangles from the line grid."""
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    if np.median(g) < 128: g = 255 - g                               # dark theme -> light
    h, w = g.shape
    bg = int(np.bincount(g.ravel()).argmax())                        # page background level
    t = thr if thr is not None else bg - 12                          # anything darker = ink (borders, text)
    ink = (g < t).astype(np.uint8) * 255
    hk = cv2.getStructuringElement(cv2.MORPH_RECT, (max(15, w // 12), 1))
    vk = cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(15, h // 14)))
    lines = cv2.bitwise_or(cv2.morphologyEx(ink, cv2.MORPH_OPEN, hk), cv2.morphologyEx(ink, cv2.MORPH_OPEN, vk))
    lines = cv2.dilate(lines, np.ones((3, 3), np.uint8))
    cnts, _ = cv2.findContours(lines, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
    boxes = []
    for c in cnts:
        x, y, bw, bh = cv2.boundingRect(c)
        if bw > 0.12 * w and bh > 0.05 * h and bw < 0.97 * w:
            boxes.append((x, y, bw, bh))
    out = []
    for bx in sorted(boxes, key=lambda b: (b[1], b[0])):
        if not any(abs(bx[0]-o[0]) < 0.01*w and abs(bx[1]-o[1]) < 0.01*h and abs(bx[2]-o[2]) < 0.015*w and abs(bx[3]-o[3]) < 0.015*h for o in out):
            out.append(bx)
    norm = [tuple(round(v, 3) for v in (x / w, y / h, bw / w, bh / h)) for x, y, bw, bh in out]
    return t, norm

def variants(img):
    yield 'orig', img
    yield 'x0.6', cv2.resize(img, None, fx=0.6, fy=0.6, interpolation=cv2.INTER_AREA)
    yield 'x1.5', cv2.resize(img, None, fx=1.5, fy=1.5, interpolation=cv2.INTER_CUBIC)
    yield 'invert', 255 - img

if __name__ == '__main__':
    for f in sorted(glob.glob('dataset/evidence/images/*.png')):
        img = cv2.imread(f); base = None
        print(os.path.basename(f))
        for name, v in variants(img):
            t, p = panels(v)
            if base is None: base = p
            same = len(p) == len(base) and all(max(abs(a - b) for a, b in zip(x, y)) < 0.01 for x, y in zip(p, base))
            print(f"   {name:<7} thr={t:>4} panels={len(p):>2} same_as_orig={same}  {p[:6]}")
