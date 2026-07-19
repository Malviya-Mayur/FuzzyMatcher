"""
Phonetic scorer plugin for FuzzyMatcher Studio.

Uses Soundex phonetic encoding before comparing with fuzz.ratio.
This helps match names that sound the same but are spelled differently
(e.g. "Katherine" vs "Catherine", "Smith" vs "Smyth").

Requires: pip install jellyfish
Falls back gracefully if jellyfish is not installed.
"""

NAME = "Phonetic (Soundex)"

try:
    from jellyfish import soundex
    from rapidfuzz import fuzz

    def score(s1: str, s2: str) -> float:
        """Encode both strings as Soundex then compare phonetically."""
        try:
            sx1 = soundex(s1) if s1.strip() else s1
            sx2 = soundex(s2) if s2.strip() else s2
            return fuzz.ratio(sx1, sx2)
        except Exception:
            return 0.0

except ImportError:
    def score(s1: str, s2: str) -> float:
        """jellyfish not installed — returns 0 for all pairs."""
        return 0.0