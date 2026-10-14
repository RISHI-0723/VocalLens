"""Feature computation tests on known synthetic signals (ARCHITECTURE §8.5)."""
import numpy as np
import pytest

from vocallens.features import (
    detect_pauses,
    estimate_noise_floor,
    frame_rms_dbfs,
    hz_to_semitones,
    median_iqr,
    pitch_variability_iqr_semitones,
    recording_energy_stats,
    relative_energy_zrel,
    syllable_count,
    word_rate,
)


def test_rms_dbfs_of_full_scale_sine(analysis_config):
    sr = 16000
    t = np.arange(sr) / sr
    y = (1.0 * np.sin(2 * np.pi * 150 * t)).astype(np.float32)
    _, db = frame_rms_dbfs(y, sr, analysis_config)
    # RMS of a unit sine = 1/sqrt(2) -> about -3.01 dBFS.
    assert np.isclose(np.median(db), -3.01, atol=0.5)


def test_rms_dbfs_of_silence_hits_floor(analysis_config):
    sr = 16000
    y = np.zeros(sr, dtype=np.float32)
    _, db = frame_rms_dbfs(y, sr, analysis_config)
    assert np.all(db <= analysis_config.framing.rms_floor_dbfs + 1e-6)


def test_semitone_conversion_octave():
    semis = hz_to_semitones(np.array([100.0, 200.0]))
    # One octave = 12 semitones.
    assert np.isclose(semis[1] - semis[0], 12.0, atol=1e-6)


def test_pitch_iqr_constant_f0_near_zero(analysis_config):
    f0 = np.full(100, 130.0)
    voiced = np.ones(100, dtype=bool)
    med, iqr, cov, valid = pitch_variability_iqr_semitones(f0, voiced, analysis_config, 100)
    assert valid
    assert iqr < 1e-6
    assert np.isclose(med, 130.0)


def test_pitch_unavailable_below_voiced_coverage(analysis_config):
    f0 = np.array([130.0, np.nan, np.nan, np.nan, np.nan])
    voiced = np.array([True, False, False, False, False])
    med, iqr, cov, valid = pitch_variability_iqr_semitones(f0, voiced, analysis_config, 5)
    assert not valid
    assert iqr is None


def test_relative_energy_uses_iqr_floor(analysis_config):
    # Near-constant IQR -> denominator clamped to floor, not exploded/zero.
    z = relative_energy_zrel(-20.0, -25.0, 0.0, analysis_config)
    assert np.isclose(z, 5.0 / analysis_config.features.energy_iqr_floor_db)


def test_zrel_invariant_to_uniform_loudness_but_sensitive_to_relative_change(analysis_config):
    """Controlled experiment (ARCHITECTURE §8.5 energy normalization, Track C).

    Documents WHY a uniform amplitude drop (the synthetic ``energy_drop`` fixture)
    is not detectable by the within-recording ``z_rel`` metric, while a
    phrase-RELATIVE energy change is. This is a correctness property of the
    metric, not a defect: z_rel standardizes against the recording's own
    median/IQR specifically to be invariant to global gain/distance.
    """
    # A recording with three phrase regions at distinct dBFS levels.
    phrase_a = np.full(60, -18.0)
    phrase_b = np.full(60, -20.0)
    phrase_c = np.full(60, -22.0)
    rec = np.concatenate([phrase_a, phrase_b, phrase_c])
    rec_med, rec_iqr = median_iqr(rec)
    z_b = relative_energy_zrel(float(np.median(phrase_b)), rec_med, rec_iqr, analysis_config)

    # (1) UNIFORM loudness drop: subtract 10 dB from EVERY frame (≈ x0.3 amplitude).
    off = -10.0
    rec_u = rec + off
    rec_med_u, rec_iqr_u = median_iqr(rec_u)
    z_b_u = relative_energy_zrel(float(np.median(phrase_b + off)), rec_med_u, rec_iqr_u, analysis_config)
    assert np.isclose(z_b, z_b_u, atol=1e-9)  # invariant: the flaw is invisible to z_rel

    # (2) PHRASE-RELATIVE drop: lower ONLY phrase C by 10 dB, others unchanged.
    rec_r = np.concatenate([phrase_a, phrase_b, phrase_c + off])
    rec_med_r, rec_iqr_r = median_iqr(rec_r)
    z_c = relative_energy_zrel(float(np.median(phrase_c)), rec_med, rec_iqr, analysis_config)
    z_c_r = relative_energy_zrel(float(np.median(phrase_c + off)), rec_med_r, rec_iqr_r, analysis_config)
    # Sensitive, but only modestly: the recording IQR inflates when one phrase
    # drops, damping the z_rel shift (z_c -0.5 -> ~-0.86). This damping is exactly
    # why energy-dynamics recall is low on the pilot (see docs/technical_report.md).
    assert z_c_r < z_c - 0.2


def test_pause_detection_merges_and_min_duration(analysis_config):
    sr = 16000
    hop = analysis_config.framing.hop_length_ms / 1000.0
    n = 400
    times = np.arange(n) * hop
    db = np.full(n, -10.0)  # speech level
    # One long silent block (~0.5 s) and one tiny 0.05 s blip.
    db[100:150] = -60.0  # 0.5 s silence
    db[200:205] = -60.0  # 0.05 s -> below min pause
    nf, _ = estimate_noise_floor(db, analysis_config)
    pauses = detect_pauses(times, db, nf, analysis_config)
    durations = [b - a for a, b in pauses]
    min_dur = analysis_config.pause_detection.min_pause_duration_ms / 1000.0
    assert any(d >= 0.25 for d in durations)
    assert all(d >= min_dur - 1e-9 for d in durations)


def test_word_rate_zero_duration_is_none():
    assert word_rate(5, 0.0) is None
    assert word_rate(0, 2.0) is None
    assert np.isclose(word_rate(6, 2.0), 3.0)


def test_syllable_count_known_words():
    assert syllable_count("water") == 2
    assert syllable_count("cat") == 1
    assert syllable_count("zzzxq-not-a-word") is None


def test_median_iqr_ignores_nan():
    med, iqr = median_iqr(np.array([1.0, np.nan, 3.0]))
    assert med == 2.0
