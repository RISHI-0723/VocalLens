"""Transcript normalization/tokenization tests (ARCHITECTURE §8.2)."""
from vocallens.transcript import normalize_token, normalize_transcript, tokenize


def test_basic_tokenization():
    _, toks = normalize_transcript("The quick brown fox.")
    assert [t.text for t in toks] == ["the", "quick", "brown", "fox"]
    assert toks[0].original == "The"


def test_contractions_and_hyphens_preserved():
    _, toks = normalize_transcript("don't state-of-the-art")
    assert [t.text for t in toks] == ["don't", "state-of-the-art"]


def test_numbers_preserved():
    _, toks = normalize_transcript("It cost 3.5 dollars.")
    assert "3.5" in [t.text for t in toks]


def test_case_and_punct_normalization():
    assert normalize_token("Hello,") == "hello"
    assert normalize_token("END.") == "end"
    assert normalize_token("3.5") == "3.5"  # decimal period kept


def test_curly_apostrophe_normalized():
    _, toks = normalize_transcript("don’t")
    assert toks[0].text == "don't"


def test_char_spans_align_to_original():
    text = "Hello world"
    _, toks = normalize_transcript(text)
    assert text[toks[1].char_start:toks[1].char_end] == "world"


def test_empty_transcript_tokenizes_to_nothing():
    _, toks = normalize_transcript("   ")
    assert toks == []
