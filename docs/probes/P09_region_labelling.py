"""P09 - Label detected rectangles into the user's 5 semantic regions using geometry only.
Two images per screenshot (user's design):
  * geometry image: grayscale -> background-relative threshold -> long-line morphology -> rectangles
  * text image:     grayscale -> contrast curve (OCR is run on this one, never on the edge image)
Labelling heuristics (user's proposal):
  green  = largest rectangle (main table panel)
  red    = KPI strip: >=3 similar boxes on one row, wide (w > h), above green
  blue   = right-column panel nearest the top (detail key/value panel)
  yellow = right-column panel below blue (activity timeline)
  black  = header band: from the top of the content area down to red
Run from repo root: python docs/probes/P09_region_labelling.py
"""
import glob, os
import cv2, numpy as np

def rects(img):
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    if np.median(g) < 128: g = 255 - g
    h, w = g.shape
    # v3: thin dark lines detected with a black-hat transform (closing - image), which measures
    # darkness *relative to the local neighbourhood*. Survives low-contrast dark themes and downscaling,
    # where an absolute 'background - 12' threshold lost the 1px borders (dark image at 0.6x).
    g = cv2.normalize(g, None, 0, 255, cv2.NORM_MINMAX)                 # contrast stretch (user step 1)
    bh_ = cv2.morphologyEx(g, cv2.MORPH_BLACKHAT, cv2.getStructuringElement(cv2.MORPH_RECT, (7, 7)))
    ink = (bh_ > 3).astype(np.uint8) * 255
    hl = cv2.morphologyEx(ink, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (max(12, w // 20), 1)))
    vl = cv2.morphologyEx(ink, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(12, h // 25))))
    grid = cv2.dilate(cv2.bitwise_or(hl, vl), np.ones((3, 3), np.uint8))
    cnts, _ = cv2.findContours(grid, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
    out = []
    for c in cnts:
        x, y, bw, bh = cv2.boundingRect(c)
        if bw > 0.08 * w and bh > 0.04 * h and bw < 0.97 * w and bh < 0.99 * h:
            if not any(abs(x-o[0]) < .01*w and abs(y-o[1]) < .01*h and abs(bw-o[2]) < .015*w and abs(bh-o[3]) < .015*h for o in out):
                out.append((x, y, bw, bh))
    return w, h, out

def label(w, h, R):
    if not R: return {}
    green = max(R, key=lambda r: r[2] * r[3])
    gx, gy, gw, gh = green
    # KPI cards: boxes entirely above green, wide, sharing (approximately) the same top and height
    above = [r for r in R if r[1] + r[3] <= gy + 5 and r[2] > r[3]]
    rows = {}
    for r in above: rows.setdefault(round(r[1] / (0.02 * h)), []).append(r)
    cards = max(rows.values(), key=len) if rows else []
    red = None
    if len(cards) >= 3:
        xs = [c[0] for c in cards]; ys = [c[1] for c in cards]
        red = (min(xs), min(ys), max(c[0] + c[2] for c in cards) - min(xs), max(c[3] for c in cards))
    # right column = panels whose left edge is right of green's right edge; drop container boxes
    right = [r for r in R if r[0] >= gx + gw - 5 and r[1] >= gy - 5]
    right = [r for r in right if not any(o != r and o[1] >= r[1] - 3 and o[1] + o[3] <= r[1] + r[3] + 3 and o[3] < r[3] * 0.9 for o in right)]
    right = [r for r in right if r[3] >= 0.06 * h]          # thin boxes are panel title bars, not panels (fix v2)
    right.sort(key=lambda r: r[1])
    blue = right[0] if right else None
    yellow = right[1] if len(right) > 1 else None
    top = 0
    black = (gx, top, w - gx, (red[1] if red else gy) - top)
    return {'black': black, 'red': red, 'green': green, 'blue': blue, 'yellow': yellow, 'n_cards': len(cards)}

def norm(b, w, h):
    return None if b is None else tuple(round(v, 3) for v in (b[0] / w, b[1] / h, b[2] / w, b[3] / h))

if __name__ == '__main__':
    tot = ok = 0
    for f in sorted(glob.glob('dataset/evidence/images/*.png')):
        img = cv2.imread(f); base = None
        for name, v in (('orig', img), ('x0.6', cv2.resize(img, None, fx=.6, fy=.6, interpolation=cv2.INTER_AREA)),
                        ('x1.5', cv2.resize(img, None, fx=1.5, fy=1.5, interpolation=cv2.INTER_CUBIC)), ('invert', 255 - img)):
            w, h, R = rects(v); L = label(w, h, R)
            n = {k: norm(L.get(k), w, h) for k in ('red', 'green', 'blue', 'yellow')}
            if base is None: base = n
            same = all((n[k] is None) == (base[k] is None) and (n[k] is None or max(abs(a - b) for a, b in zip(n[k], base[k])) < 0.015) for k in n)
            tot += 1; ok += same
            print(f"{os.path.basename(f)[:34]:<34} {name:<6} cards={L.get('n_cards',0)} same={same} red={n['red']} green={n['green']} blue={n['blue']} yellow={n['yellow']}")
    print(f"\nconsistent with original: {ok}/{tot}")
