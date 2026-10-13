"""Shared pytest fixtures for VocalLens tests."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from vocallens.config import load_analysis_config, load_scoring_config  # noqa: E402


@pytest.fixture(scope="session")
def analysis_config():
    return load_analysis_config()


@pytest.fixture(scope="session")
def scoring_config():
    return load_scoring_config()


@pytest.fixture
def tone_wav(tmp_path):
    """Factory writing a mono tone WAV; returns (path, duration)."""
    import soundfile as sf

    def _make(freq=150.0, duration=2.0, sr=16000, amp=0.3, name="tone.wav"):
        t = np.arange(int(duration * sr)) / sr
        y = amp * np.sin(2 * np.pi * freq * t).astype(np.float32)
        p = tmp_path / name
        sf.write(str(p), y, sr, subtype="PCM_16")
        return str(p), duration

    return _make
