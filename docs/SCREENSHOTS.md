# Screenshot evidence: layout model and extraction plan (P05, P06)

Planning document, not a deliverable.

## 1. Layout model (the user's 5-component reading, verified by P05)
The 10 light screenshots come from **one pixel-identical template**. The panel borders sit at the same coordinates in every image: sidebar ends at x=222, header ends at y≈204, the KPI strip spans y≈220–297, the main area starts at y≈313, the table panel spans x 246–1411, and the side panels span x 1426/1445–1775. The one exception is width: `marketing_profile_console.png` is 1500 px wide, so its right panel shifts left by exactly 300 px. Panel positions should therefore be detected from the border lines, not hard-coded.

| # | Component | Content | Extraction notes |
|---|---|---|---|
| 1 | Header (black) | breadcrumb, page title, badge (e.g. "4 jobs", "Live"), subtitle. Profile screens put the entity id + identifiers here (`marketing_001 · sj.park@naver.com · +82 …`) | Free-text line, regex for ids, emails and phones |
| 2 | Tabs + KPI strip (red) | 4–5 cards of `label / value`. The sparklines are decorative because each card prints its value | Label row + value row |
| 3 | Main table (green) | Header row + N records. **Most rows are decoys** (other customers, or `@northstar.shop` staff) | Column x-positions from the header row; rows by y |
| 4 | Detail panel (blue) | `label: value` pairs for **the record of interest**. In the export screen this is `export_1260`, *not* the highlighted first table row | Two-column key/value |
| 5 | Activity timeline (yellow) | `time / event` pairs | Pairs of lines |

The dark `security_audit_explorer_20260905.png` is the **same template in a dark theme**: after auto-inversion, P09 finds the same 5 regions. *(Corrected by P09; P05 had measured it without inversion.)*

## 2. P06 trial: region crop + 2× upscale + tesseract TSV, cells rebuilt from word boxes
On `customer_export_console_20260618.png` the result was almost entirely correct: the header, the KPIs, all 4 table rows, 7/8 detail fields, and all 4 timeline events. **Two failures matter:** the owner email in table row 2 (the subject's row) was dropped, and the value "0" next to `Download count` was lost. In both cases a critical cell went silently missing, which is exactly where the risk lies.

## 3. Options for decision C
| Option | Accuracy | Determinism / cost | Risk |
|---|---|---|---|
| OCR only (template regions + TSV) | High on text, misses some cells | Free, repeatable | Silent misses on key identifiers |
| Vision LLM per image (or per region crop) → strict JSON schema | Highest | 11 calls once, cached; tiny cost | Hallucinated or altered identifiers |
| **Both, cross-checked** | Highest + verified | 11 calls + OCR | Disagreements need a rule |

Proposed cross-check rule (if hybrid): an identifier (email, phone, `*_NNN` id, `user_NN`) is accepted only if the LLM output contains it **and** it appears in the OCR text, or it matches a known identity or resource id in the CSVs. Otherwise it is flagged and the LLM value is kept with low confidence.

## 4. Robustness to unseen screenshots (user question, 2026-10-24 21:50)
Risk: hidden or post-submission evidence may differ in zoom, font, theme or layout. Template coordinates would then break silently.
Design principles derived:
1. **No coordinates in the solution.** The 5-component model becomes a *semantic* schema (entity header, KPI pairs, tables, key/value detail, timeline, plus a catch-all list of every identifier seen). Nothing positional.
2. **Primary reader = vision LLM** on the whole image. It is layout, zoom, font and theme agnostic.
3. **Verifier = layout-agnostic OCR** on the whole image with adaptive preprocessing: invert when mean luminance < 128, rescale so text height lands in tesseract's sweet spot (~30 px cap height), `--psm 11`. It is used **only** as a bag of tokens to confirm identifiers, never for structure.
4. **Generic identifier harvesting** (regex for emails, phones, `*_NNN` ids, `user_NN`, 64-hex hashes) runs on every evidence type, so an unseen format still contributes links.
5. **Cache keyed by file content hash.** New or changed images are re-extracted automatically. Unchanged ones cost nothing.
6. **Graceful degradation:** if no LLM is available, OCR-token identifier harvesting still runs, with structure-dependent facts marked low-confidence.
7. **Custom evaluation cases** (also satisfies the "≥3 additional evaluation cases" requirement): rescaled (0.6×, 1.5×), dark-inverted and font-substituted variants of existing screenshots. The extracted identifiers must match the originals.

## 5. User-proposed CV segmentation (Krita experiment → P07, P08)
User pipeline: grayscale → contrast S-curve → threshold (210) → edge detection (simple, all sides) → panel rectangles. Without the threshold, the table row borders are also kept.

**P07 implementation** (`docs/probes/P07_cv_segmentation.py`), generalised so it does not depend on one theme or scale:
- auto-invert when the median luminance is < 128 (dark theme);
- threshold **relative to the page background** (most frequent grey − 12) instead of a fixed 210. A first attempt with Otsu found 0 panels, because the light-grey borders fell on the "background" side;
- long-line morphology with kernels proportional to the image size (w/12, h/14) instead of Canny, keeping only border lines, then rectangles from the line grid.

**Results on 11 PNGs × 4 variants (orig, 0.6×, 1.5×, inverted):**
- Light template: the same 5 panels (table panel, side column, detail panel, table body, activity panel) in normalised coordinates for **orig, 1.5× and inverted in 10/10 images**.
- 0.6× downscale: same panels **plus** extra boxes from table-row borders (a superset, not a loss).
- KPI cards are found only in `marketing_profile_console` (size filter), so they need a separate rule.
- Dark `security_audit_explorer`: works for orig, 1.5× and inverted; **fails at 0.6×** (0 panels).
- The rectangles are geometric, not semantic. Deciding which box is the table, detail or timeline needs content cues (header row, label:value pairs, time stamps).

**P08 row-strip OCR** (user's "row borders" point turned into a feature): split the table panel at detected horizontal row lines and OCR each strip with `--psm 7`. All 6 strips (title, header, 4 rows) were read correctly, **including `ingrid.dahl@outlook.com` in row 2, which full-panel OCR (P06) had dropped**.

**Takeaway:** the CV path is scale- and theme-tolerant for panel and row structure, and it fixes the silent-miss problem for tables. Panel semantics and odd templates (dark screen at small scale) are where a vision LLM still adds value.

## 6. Two-image design + geometric region labelling (user proposal → P09)
User design: **two derived images per screenshot.**
1. **Text image:** grayscale + contrast curve. OCR runs *only* on this one, because edge detection garbles glyphs.
2. **Geometry image:** threshold + border detection, used only to find rectangles.

The two are correlated by coordinates: each OCR word box is assigned to the region that contains it.

Labelling heuristics (the user's, plus one fix):
| Region | Rule | Result |
|---|---|---|
| green (table) | largest rectangle | 44/44 consistent |
| red (KPI strip) | ≥3 wide boxes (w>h) sharing a row, above green; union of them | 43/44 (4–6 cards found) |
| blue (detail) | right-column panel nearest the top, right of green | — |
| yellow (activity) | next right-column panel below blue | — |
| black (header) | band from the content top to red | derived |

- **Fix v2:** the right column also contains a thin **title bar** (h ≈ 0.04 of the image) holding the record id (`backup_9287`, `export_1260`). Without the fix it was mislabelled as blue in 8/11 images. Thin boxes (h < 0.06) are excluded from the blue/yellow ordering **but must be merged into blue** when extracting, because the title bar carries the record of interest.
- **After the fix: 43/44 variants give the same labels as the original.** The only failure is the dark screenshot at 0.6×, where segmentation finds nothing; the fallback is the vision LLM.
- **Semantic check:** OCR of the yellow region starts with "Activity" in **11/11** originals, and blue holds `label value` pairs in 11/11.
- **Coordinates are only used relatively** (largest box, left/right of green, top-to-bottom order), never as absolute pixel positions, so zoom and theme changes are tolerated.

## 7. Conditional invert for dark themes, and fixing the last failure (P09 v3)
**User rule:** if the background is dark and the font white, invert the image first. This is applied to *both* derived images (text and geometry) when the median luminance is < 128.

Diagnosis of the remaining failure (dark screenshot at 0.6×), after inversion:
- Dark theme has low internal contrast: page 234, panel fill 227, border 202.
- At 0.6× the 1-px border blurs to 221–222, only 5 levels below the fill. The absolute "background − 12" threshold therefore lost it.

**Fix (v3):**
1. Contrast stretch to the full 0–255 range (the user's contrast step, applied before geometry too).
2. Detect borders with a **black-hat transform** (closing − image). This measures darkness *relative to the local neighbourhood*, not absolute grey, and uses a low threshold (>3). The long-line morphology then discards text and noise.

**Result: 44/44 variants (11 screenshots × original, 0.6×, 1.5×, inverted) give labels identical to the original.** Semantic check: the yellow region OCR starts with "Activity" in 21/22 (original + 0.6×). The single miss is OCR of tiny 0.6× text, not segmentation.

### Final geometry pipeline (for the design)
`load → grayscale → [median < 128 ? invert] → contrast stretch → black-hat (7×7) > 3 → long-line opening (w/20 horizontal, h/25 vertical) → line grid → rectangles → labels (green: largest; red: ≥3 wide cards above green; right column top-down, thin title bars merged into blue: blue, yellow; black: band above red)`
Text pipeline: `grayscale → [invert] → contrast curve → upscale so text height ≈ 30 px → per-region OCR (row strips for green)`.
