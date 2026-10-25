"""P05 - Layout uniformity of evidence screenshots.
Detects bordered panels (light-grey 1px borders on the white canvas) in each PNG
and reports their boxes, so we can check whether the 5-component layout
(header, status/KPI strip, table, detail panel, activity timeline) is uniform.
Run from repo root: python docs/probes/P05_screenshot_layout.py
"""
import glob, os
from PIL import Image
import numpy as np

def panels(path):
    im = np.asarray(Image.open(path).convert('L')).astype(int)
    h, w = im.shape
    side = int(np.argmax(im[h // 2, :] > 200))            # end of dark sidebar
    border = (im > 200) & (im < 240)                         # light-grey border pixels
    rows = [y for y in range(h) if border[y, side:].sum() > 0.15 * (w - side)]
    cols = [x for x in range(side, w) if border[:, x].sum() > 0.12 * h]
    def runs(v):
        out, s = [], None
        for a, b in zip(v, v[1:] + [None]):
            s = a if s is None else s
            if b is None or b - a > 3: out.append((s + a) // 2); s = None
        return out
    return w, h, side, runs(rows), runs(cols)

for f in sorted(glob.glob('dataset/evidence/images/*.png')):
    w, h, side, hr, vc = panels(f)
    print(f"{os.path.basename(f):<44} {w}x{h} sidebar_end={side:<4} h-lines={hr[:12]} v-lines={vc[:10]}")
