"""Screenshot evidence (DESIGN §5.1 / D5 / D5a).

TODO(M5): geometry + OCR pipeline with the conditional vision-LLM pass (port docs/probes/P09_region_labelling.py).
For M2 every PNG is registered as unparsed so the file is accounted for but contributes no facts.
Rules: W-EVD-04, H-IDN-04.
"""
from __future__ import annotations

from pathlib import Path

from ..loaders import EvidenceFile
from . import ParsedFile


def parse_image(f: EvidenceFile, path: Path) -> ParsedFile:
    return ParsedFile("png", unparsed_reason="TODO(M5): screenshot pipeline (D5) not implemented yet")
