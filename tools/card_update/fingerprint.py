"""Fingerprint of the scoring code that computes the stored IER.

IER is written by scoring/build_store.py from simmander_scoring.evaluate
(isolated_efficiency_rating), which uses simmander_scoring.mechanics; the package
__init__ re-exports both. A change to any of these files can legitimately change the IER
of an unchanged card, so the IER-stability gate is only enforced while the fingerprint
recorded with the live release equals the fingerprint of the code building the candidate.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

IER_CODE_FILES = (
    "scoring/build_store.py",
    "scoring/simmander_scoring/__init__.py",
    "scoring/simmander_scoring/evaluate.py",
    "scoring/simmander_scoring/mechanics.py",
)
UNKNOWN = "unknown"   # live store built by unrecorded code (init --baseline-from-store)


def scoring_fingerprint(app_dir: Path) -> str:
    h = hashlib.sha256()
    for rel in sorted(IER_CODE_FILES):
        data = (Path(app_dir) / rel).read_bytes().replace(b"\r\n", b"\n")   # checkout-EOL independent
        h.update(rel.encode() + b"\0" + hashlib.sha256(data).digest())
    return h.hexdigest()
