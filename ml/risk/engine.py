"""RiskEngine: configurable, documented mapping from event descriptors to LOW / MODERATE / SEVERE.

What   : rule-based composite scoring. NOT an official warning system: categories are analytical only.
Input  : intensity, probability, duration, affected area (+ horizon and uncertainty for the confidence label).
Output : category, composite score in [0, 1], component breakdown and human-readable rationale.
Math   : each driver d is scaled s_d = clip((x_d - lo_d) / (hi_d - lo_d), 0, 1) with (lo, hi) from
         ``config/risk.yaml``; hazard = sum_d w_d s_d (weights sum to 1); score = probability^gamma * hazard;
         category = SEVERE if score >= t_severe, MODERATE if >= t_moderate, else LOW.
Limits : all scales/weights/thresholds are demonstration defaults, not calibrated against impacts.
         Forecast horizon and uncertainty do NOT change the category; they set the confidence label.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from ml.core.config import load_config
from ml.core.provenance import config_hash
from ml.uncertainty.ensemble import confidence_class


@dataclass(frozen=True)
class RiskInputs:
    event_type: str
    peak_intensity: float
    probability: float
    duration_h: float
    area_km2: float
    forecast_horizon_h: float
    uncertainty_radius_km: float
    member_agreement: float


@dataclass(frozen=True)
class RiskAssessment:
    category: str
    score: float
    hazard: float
    components: dict[str, float]
    confidence: str
    rationale: list[str] = field(default_factory=list)
    disclaimer: str = ""
    config_digest: str = ""


def _scale(x: float, lo: float, hi: float) -> float:
    return float(np.clip((x - lo) / (hi - lo), 0.0, 1.0))


class RiskEngine:
    """Evaluate :class:`RiskInputs` against the configured scales."""

    def __init__(self, config: dict | None = None) -> None:
        self.cfg = config or load_config("risk")
        w = self.cfg["weights"]
        if abs(sum(w.values()) - 1.0) > 1e-9:
            raise ValueError("risk weights must sum to 1")

    def assess(self, r: RiskInputs) -> RiskAssessment:
        scales = self.cfg["scales"].get(r.event_type)
        if scales is None:
            raise ValueError(f"No risk scales configured for event type {r.event_type!r}")
        if not 0.0 <= r.probability <= 1.0:
            raise ValueError("probability must lie in [0, 1]")
        w = self.cfg["weights"]
        comp = {
            "intensity": _scale(r.peak_intensity, scales["intensity"]["lo"], scales["intensity"]["hi"]),
            "area": _scale(r.area_km2, scales["area_km2"]["lo"], scales["area_km2"]["hi"]),
            "duration": _scale(r.duration_h, scales["duration_h"]["lo"], scales["duration_h"]["hi"]),
        }
        hazard = sum(w[k] * v for k, v in comp.items())
        score = float(r.probability ** self.cfg["probability_exponent"] * hazard)
        t = self.cfg["category_thresholds"]
        category = "SEVERE" if score >= t["severe"] else "MODERATE" if score >= t["moderate"] else "LOW"
        conf = confidence_class(r.member_agreement, r.uncertainty_radius_km)
        unit = scales["intensity"]["unit"]
        rationale = [
            f"Peak intensity {r.peak_intensity:.0f} {unit} -> intensity factor {comp['intensity']:.2f}",
            f"Affected area {r.area_km2:,.0f} km2 -> area factor {comp['area']:.2f}",
            f"Duration {r.duration_h:.0f} h -> duration factor {comp['duration']:.2f}",
            f"Probability {r.probability:.2f}; composite score {score:.2f} "
            f"(MODERATE >= {t['moderate']}, SEVERE >= {t['severe']})",
            f"Confidence {conf}: member agreement {r.member_agreement:.2f}, "
            f"position uncertainty {r.uncertainty_radius_km:.0f} km at +{r.forecast_horizon_h:.0f} h",
        ]
        return RiskAssessment(category, score, float(hazard), comp, conf, rationale,
                              str(self.cfg["disclaimer"]).strip(), config_hash(self.cfg))
