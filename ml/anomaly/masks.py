"""Three-class anomaly masks: 0 = normal, 1 = moderate, 2 = extreme."""
from __future__ import annotations

import numpy as np

from ml.anomaly.detectors import Thresholds

NORMAL, MODERATE, EXTREME = 0, 1, 2


def classify(score: np.ndarray, thresholds: Thresholds, two_sided: bool = False) -> np.ndarray:
    """Classify ``score`` into normal / moderate / extreme (NaN -> normal, never silently 'extreme').

    ``two_sided=True`` uses ``|score|`` (for signed scores such as z-scores of temperature).
    """
    s = np.abs(score) if two_sided else np.asarray(score, float)
    out = np.zeros(s.shape, dtype=np.uint8)
    valid = np.isfinite(s)
    out[valid & (s >= thresholds.moderate)] = MODERATE
    out[valid & (s >= thresholds.extreme)] = EXTREME
    return out
