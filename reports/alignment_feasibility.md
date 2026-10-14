# Alignment Feasibility Report

**Original date:** 2026-10-13
**Revised:** 2026-10-13 (re-investigation; corrects the earlier dependency-conflict claim with reproduced evidence).
**Environment:** Windows 11, Python 3.11.9 (CPU only).
**Budget:** 30-minute focused feasibility window (ARCHITECTURE.md §5).

## What was attempted
1. Installed WhisperX as the canonical primary aligner (`whisperx==3.8.6`).
2. Implemented a forced-alignment adapter (`src/vocallens/alignment.py`) with a
   real `whisperx` backend, a `provided` backend for synthetic fixtures, and
   explicit `unavailable`/`timed_out`/`failed` states that never fabricate
   timestamps.
3. **Re-investigated the reported blocker directly** (see below), because the
   first report asserted a hard dependency conflict that had not been reproduced.

## Actual outcomes (reproduced 2026-10-13)

### The reported protobuf/numpy dependency conflict is NOT reproduced
The earlier report claimed WhisperX forces `numpy>=2.1` and `protobuf>=7`, which
would break Streamlit's `protobuf<7` pin. Direct inspection of the installed
environment contradicts this:

- `whisperx==3.8.6`, `streamlit==1.45.1`, `protobuf==6.33.6` (**< 7**),
  `numpy==1.26.4` (**< 2**), and `torch==2.8.0` are **installed together and
  import together** in one interpreter (`import streamlit, whisperx` both
  succeed).
- Streamlit's declared pins are `protobuf<7,>=3.20` and `numpy<3,>=1.23`; the
  installed `protobuf 6.33.6` and `numpy 1.26.4` satisfy them.
- WhisperX 3.8.6's declared dependencies list plain `numpy` (unpinned) — it does
  **not** force `numpy>=2.1` or `protobuf>=7`.

**Conclusion:** there is no genuine protobuf/numpy conflict between WhisperX
3.8.6 and the dashboard stack in this environment. The earlier claim was
incorrect and is retracted. (WhisperX does still pull a large stack — torch,
torchaudio, pyannote-audio, transformers, ctranslate2 — so it remains an
optional, separately-installed extra in `requirements-align.txt` on download-size
grounds, not because of a version conflict.)

### The alignment model asset loads
`whisperx.load_align_model(language_code="en", device="cpu")` **downloaded and
loaded successfully** (a 360 MB wav2vec2 English alignment model, ~112 s on first
download; cached thereafter). `metadata` returns keys `language`, `dictionary`,
`type`. Model-asset availability is therefore **not** a blocker in this
environment.

### The real runtime blocker was a missing ffmpeg binary — now fixed
With deps and model present, the adapter still returned `unavailable` with
`FileNotFoundError: [WinError 2]`. Root cause: `whisperx.load_audio()` shells out
to an **ffmpeg** binary, which is not installed (`ffmpeg` is not on PATH). The
adapter correctly degraded to an explicit `unavailable` state and **did not
fabricate timestamps**.

Fix applied: the WhisperX backend now decodes audio with the project's own
soundfile/librosa decoder (`audio_io.load_audio`) at the analysis sample rate,
instead of `whisperx.load_audio()`. This removes the ffmpeg hard-dependency and
aligns against the same analysis copy the features use. After the fix, the
adapter runs end to end (`whisperx.align()` executes and returns word-level
timings).

### What is still NOT verified
Forced-alignment **accuracy on real speech** remains **unverified** because no
licensed/consented real English speech is available in this environment, and no
audio may be downloaded without verified licensing/consent. The pilot dataset is
synthetic tonal fixtures with no phonetic content; running WhisperX against them
exercises the code path but does **not** produce an interpretable
alignment-accuracy result, so it is not reported as one.

## Decision (honest, within spec)
- For the synthetic pilot the pipeline uses the `provided` ground-truth backend
  (labeled, not forced-alignment output).
- The WhisperX adapter is implemented, decodes without ffmpeg, and runs end to
  end; it will perform real forced alignment when real speech + a transcript are
  supplied and WhisperX is installed from `requirements-align.txt`.
- No word timestamps are ever fabricated when alignment is unavailable.

## Status
- **Dependency conflict:** NOT a blocker (claim retracted; reproduced coexistence).
- **Model asset:** available (loads on CPU).
- **ffmpeg dependency:** removed from the VocalLens WhisperX path (adapter fix +
  regression test `tests/test_alignment.py::test_whisperx_decode_is_ffmpeg_free_and_analysis_rate`).
- **Real-speech forced-alignment accuracy:** **BLOCKED / NOT VERIFIED** — no
  licensed real-speech data. This is the single remaining blocker.

**Reproducible next step:** install `requirements-align.txt` in an environment,
supply a short licensed real-speech clip plus its transcript, call
`analyze_pair(... alignment_backend="whisperx")`, and record aligned-token
coverage and temporal error against a reviewed reference.
