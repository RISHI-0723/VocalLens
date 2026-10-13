"""Evidence-grounded explanation generation (ARCHITECTURE.md §8.8).

Explanations are built only from computed values and rule outcomes. They state
what changed, where, the participant/reference values, the triggering rule, and
what cannot be concluded. They never invent acoustic observations and never
claim a measured delta proves intent, confidence, or audience impact.
"""
from __future__ import annotations

from .schemas import Detection, DetectionFamily, Severity

_UNIT_WORDS = {
    "words_per_second": "words/s",
    "seconds": "s",
    "semitones": "semitone(s)",
    "zscore": "SD (within-recording)",
}

_FAMILY_CAVEAT = {
    DetectionFamily.PACE: (
        "A pace difference may reflect intentional pacing or style; it does not by "
        "itself indicate worse delivery."
    ),
    DetectionFamily.PAUSE: (
        "A longer or shorter pause may be intentional emphasis; pause boundaries also "
        "depend on the noise floor and the detector settings."
    ),
    DetectionFamily.PITCH_VARIATION: (
        "Pitch variability depends on voicing and can be affected by the recording; a "
        "wider or narrower range is not inherently better or worse."
    ),
    DetectionFamily.ENERGY_DYNAMICS: (
        "Relative energy reduces some gain differences but cannot fully correct for "
        "microphone distance or room; a difference is not proof of emphasis or projection."
    ),
}

_FAMILY_TITLE = {
    DetectionFamily.PACE: "Pace differs from reference",
    DetectionFamily.PAUSE: "Pause differs from reference",
    DetectionFamily.PITCH_VARIATION: "Pitch variation differs from reference",
    DetectionFamily.ENERGY_DYNAMICS: "Energy dynamics differ from reference",
}


def title_for(detection: Detection) -> str:
    return _FAMILY_TITLE.get(detection.family, "Candidate deviation")


def build_explanation(detection: Detection) -> str:
    """Compose a human-readable, evidence-grounded explanation string."""
    unit = _UNIT_WORDS.get(detection.unit, detection.unit)
    p, r, d = detection.participant_value, detection.reference_value, detection.delta
    sign = "+" if (d is not None and d >= 0) else ""
    direction = "higher" if (d is not None and d >= 0) else "lower"
    sev = detection.severity.value
    return (
        f"In the matched phrase ({detection.participant_start:.2f}-{detection.participant_end:.2f} s "
        f"participant; {detection.reference_start:.2f}-{detection.reference_end:.2f} s reference), "
        f"the participant measured {p} {unit} and the reference {r} {unit}, "
        f"a difference of {sign}{d} {unit} ({direction} than reference). "
        f"This is {detection.normalized_exceedance:.2f}x the configured threshold "
        f"({detection.threshold} {unit}) for rule '{detection.rule_id}', a {sev} candidate deviation."
    )


def build_caveat(detection: Detection) -> str:
    base = _FAMILY_CAVEAT.get(detection.family, "")
    return (
        base + " This is a measured difference under a provisional rule, not a "
        "judgment of the speaker's ability, intent, or emotional state."
    )


def annotate(detection: Detection) -> Detection:
    detection.explanation = build_explanation(detection)
    detection.caveat = build_caveat(detection)
    return detection
