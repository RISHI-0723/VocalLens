"""Transcript normalization and tokenization (ARCHITECTURE.md §8.2).

Conservative, deterministic normalization for matching, while preserving the
original surface text and character spans for display. Contractions, hyphenated
words, and meaningful numbers are preserved as single tokens.
"""
from __future__ import annotations

import re
import unicodedata
from typing import List, Tuple

from .schemas import Token

# A token is a run of word characters that may contain internal apostrophes or
# hyphens (don't, state-of-the-art, 3.5). Surrounding punctuation is excluded.
_TOKEN_RE = re.compile(r"[0-9A-Za-zÀ-ɏ]+(?:[’'\-.][0-9A-Za-zÀ-ɏ]+)*")


def normalize_text(text: str) -> str:
    """Unicode (NFKC) + whitespace normalization, preserving characters."""
    text = unicodedata.normalize("NFKC", text)
    # Normalize curly apostrophes to straight for consistent matching.
    text = text.replace("’", "'").replace("‘", "'")
    return text


_EDGE_PUNCT = ".,!?;:\"'()[]{}-"


def normalize_token(surface: str) -> str:
    """Lowercase + strip leading/trailing punctuation; keep internal marks/decimals."""
    s = normalize_text(surface).lower()
    # Strip surrounding punctuation (also handles raw aligner words like "word,").
    # Internal apostrophes/hyphens and decimal periods are preserved because they
    # are not at a boundary (e.g. don't, state-of-the-art, 3.5).
    s = s.strip(_EDGE_PUNCT)
    return s


def tokenize(text: str) -> List[Token]:
    """Tokenize into normalized tokens with original surface forms and spans."""
    norm = normalize_text(text)
    tokens: List[Token] = []
    idx = 0
    for m in _TOKEN_RE.finditer(norm):
        surface = m.group(0)
        normalized = normalize_token(surface)
        if not normalized:
            continue
        tokens.append(
            Token(
                index=idx,
                text=normalized,
                original=surface,
                char_start=m.start(),
                char_end=m.end(),
            )
        )
        idx += 1
    return tokens


def normalize_transcript(text: str) -> Tuple[str, List[Token]]:
    """Return (original_text, tokens). The original is kept verbatim for display."""
    if text is None:
        raise ValueError("transcript must not be None")
    return text, tokenize(text)


def token_strings(tokens: List[Token]) -> List[str]:
    return [t.text for t in tokens]
