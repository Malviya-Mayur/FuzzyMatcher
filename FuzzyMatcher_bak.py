#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Fuzzy Matcher – offline fuzzy text matching between two columns from CSV/XLSX files.

For each value in the target column, finds the best-matching value in the
source column (which may come from the same file/column or a different one),
along with every source value that clears the given threshold.

Author: [Your Name]
Version: 2.0
"""

import re
import warnings
from typing import Optional, Dict, List

import numpy as np
import pandas as pd
from rapidfuzz import fuzz, process

# ----------------------------------------------------------------------
# Optional dependencies (with graceful fallback)
# ----------------------------------------------------------------------
try:
    from tqdm import tqdm
except ImportError:
    tqdm = None

try:
    from nltk.stem import PorterStemmer
    _stemmer = PorterStemmer()
except ImportError:
    _stemmer = None
    warnings.warn("nltk not installed; stemming will be disabled.", UserWarning)

# ----------------------------------------------------------------------
# Built-in English stopwords (case-insensitive)
# ----------------------------------------------------------------------
STOPWORDS = {
    "a", "about", "above", "after", "again", "against", "all", "am", "an", "and",
    "any", "are", "as", "at", "be", "because", "been", "before", "being", "below",
    "between", "both", "but", "by", "could", "did", "do", "does", "doing", "down",
    "during", "each", "few", "for", "from", "further", "had", "has", "have", "having",
    "he", "he'd", "he'll", "he's", "her", "here", "here's", "hers", "herself", "him",
    "himself", "his", "how", "how's", "i", "i'd", "i'll", "i'm", "i've", "if", "in",
    "into", "is", "it", "it's", "its", "itself", "let's", "me", "more", "most", "my",
    "myself", "nor", "of", "on", "once", "only", "or", "other", "ought", "our", "ours",
    "ourselves", "out", "over", "own", "same", "she", "she'd", "she'll", "she's",
    "should", "so", "some", "such", "than", "that", "that's", "the", "their", "theirs",
    "them", "themselves", "then", "there", "there's", "these", "they", "they'd",
    "they'll", "they're", "they've", "this", "those", "through", "to", "too", "under",
    "until", "up", "very", "was", "we", "we'd", "we'll", "we're", "we've", "were",
    "what", "what's", "when", "when's", "where", "where's", "which", "while", "who",
    "who's", "whom", "why", "why's", "with", "would", "you", "you'd", "you'll",
    "you're", "you've", "your", "yours", "yourself", "yourselves"
}

# ----------------------------------------------------------------------
# Preprocessing functions
# ----------------------------------------------------------------------
def strip_invisible(text: str) -> str:
    """
    Remove control characters, zero-width spaces, and other invisible
    non-printable characters.
    """
    return re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f\u200b-\u200f\u2028-\u202f]', '', text)


def to_display_string(value) -> str:
    """
    Convert a raw cell value to the string that should be SHOWN in the output
    (i.e. the original, un-preprocessed value). Missing/NaN cells become an
    empty string rather than the literal text "nan" — a blank input should
    stay visibly blank, not accidentally match real data.
    """
    if pd.isna(value):
        return ''
    return str(value)


def preprocess_text(text: str,
                     lowercase: bool = False,
                     trim: bool = False,
                     remove_punct: bool = False,
                     remove_stopwords: bool = False,
                     stem: bool = False) -> str:
    """
    Apply selected preprocessing steps to a string, for SCORING purposes only.
    The original (un-preprocessed) value is always what gets written to output.
    Always strips invisible characters first, regardless of other options.
    """
    if not isinstance(text, str):
        text = str(text)
    # Always strip invisible characters (safety step, not optional)
    text = strip_invisible(text)
    if lowercase:
        text = text.lower()
    if remove_punct:
        # Replace punctuation with a space (not with nothing) so that
        # "Bob-Marley" -> "Bob Marley" instead of "BobMarley". Deleting
        # punctuation outright merges tokens together and quietly breaks
        # token_sort_ratio / token_set_ratio, which rely on token boundaries.
        text = re.sub(r'[^\w\s]', ' ', text)
        text = re.sub(r'\s+', ' ', text).strip()
    if trim:
        text = text.strip()
    if remove_stopwords:
        words = text.split()
        words = [w for w in words if w.lower() not in STOPWORDS]
        text = ' '.join(words)
    if stem:
        if _stemmer is not None:
            words = text.split()
            words = [_stemmer.stem(w) for w in words]
            text = ' '.join(words)
        else:
            warnings.warn("Stemming requested but nltk not installed. Skipping.", UserWarning)
    return text


# ----------------------------------------------------------------------
# Scorer registry
# ----------------------------------------------------------------------
_SCORER_MAP = {
    "ratio": fuzz.ratio,
    "partial_ratio": fuzz.partial_ratio,
    "token_sort_ratio": fuzz.token_sort_ratio,
    "token_set_ratio": fuzz.token_set_ratio,
    "WRatio": fuzz.WRatio,
}
_SMART_SCORERS = [fuzz.ratio, fuzz.partial_ratio, fuzz.token_sort_ratio, fuzz.token_set_ratio, fuzz.WRatio]


def _score_matrix(target_batch: List[str], source_list: List[str], scorer: str, workers: int) -> np.ndarray:
    """
    Compute a (len(target_batch) x len(source_list)) similarity matrix using
    rapidfuzz's vectorized, multi-threaded cdist — this is what actually
    makes 100k-row inputs feasible, vs. a manual Python for-loop per pair.

    "smart" = element-wise max across all five standard scorers, exactly as
    agreed (ratio, partial_ratio, token_sort_ratio, token_set_ratio, WRatio).
    """
    if scorer == "smart":
        mats = [
            process.cdist(target_batch, source_list, scorer=s, workers=workers, dtype=np.float32)
            for s in _SMART_SCORERS
        ]
        return np.maximum.reduce(mats)
    if scorer not in _SCORER_MAP:
        raise ValueError(f"Unknown scorer: {scorer}. Choose from {list(_SCORER_MAP.keys())} or 'smart'.")
    return process.cdist(target_batch, source_list, scorer=_SCORER_MAP[scorer], workers=workers, dtype=np.float32)


# ----------------------------------------------------------------------
# Main matching function
# ----------------------------------------------------------------------
def fuzzy_match(
    target_file: str,
    source_file: str,
    target_col: str,
    source_col: str,
    scorer: str = "token_set_ratio",
    threshold: float = 80.0,
    preprocess_options: Optional[Dict[str, bool]] = None,
    workers: Optional[int] = None,
    batch_size: int = 500,
    output_file: Optional[str] = None
) -> pd.DataFrame:
    """
    Perform fuzzy matching between two columns from two files (CSV or XLSX).
    Target and source may point to the same file/column or different ones.

    Parameters
    ----------
    target_file : str
        Path to the file containing the target column.
    source_file : str
        Path to the file containing the source column (may be the same as target_file).
    target_col : str
        Name of the column in target_file to match.
    source_col : str
        Name of the column in source_file to match against.
    scorer : str, default "token_set_ratio"
        One of: 'ratio', 'partial_ratio', 'token_sort_ratio',
                'token_set_ratio', 'WRatio', or 'smart' (max of all five).
    threshold : float, default 80.0
        Minimum match percentage (0-100). Only matches >= threshold are kept
        in "All_Matches_Above_Threshold"; rows with no qualifying match are
        still included in the output (Best_Match/Match_Score left blank),
        never dropped.
    preprocess_options : dict, optional
        Keys: 'lowercase', 'trim', 'remove_punct', 'remove_stopwords', 'stem'.
        Values: bool. If None, all are False. These only affect SCORING —
        the output always shows values exactly as they appeared in the
        original files.
    workers : int, optional
        Number of parallel threads used internally by rapidfuzz's cdist.
        Supply -1 to use all available CPU cores. If None, uses cpu_count() - 1.
    batch_size : int, default 500
        Number of target rows scored per batch. Scoring is chunked so that
        memory use stays bounded (batch_size x len(source)) instead of
        materializing the full target x source matrix at once, which is
        important once either file approaches ~100k rows.
    output_file : str, optional
        If provided, saves the result to this path (extension .csv or .xlsx).

    Returns
    -------
    pd.DataFrame
        Columns: Target_Value, Best_Match, Match_Score, All_Matches_Above_Threshold.
        Every target row is represented, even when it has no match above
        threshold (Best_Match / Match_Score are then blank/NaN).
    """
    if preprocess_options is None:
        preprocess_options = {}
    opts = {
        'lowercase': preprocess_options.get('lowercase', False),
        'trim': preprocess_options.get('trim', False),
        'remove_punct': preprocess_options.get('remove_punct', False),
        'remove_stopwords': preprocess_options.get('remove_stopwords', False),
        'stem': preprocess_options.get('stem', False),
    }

    import multiprocessing as mp

    def load_file(filepath: str) -> pd.DataFrame:
        if filepath.endswith('.csv'):
            return pd.read_csv(filepath, sep=';')
        elif filepath.endswith(('.xlsx', '.xls')):
            return pd.read_excel(filepath, engine='openpyxl')
        else:
            raise ValueError(f"Unsupported file format: {filepath}. Use .csv, .xlsx, or .xls.")

    df_target = load_file(target_file)
    df_source = load_file(source_file)

    if target_col not in df_target.columns:
        raise ValueError(f"Target column '{target_col}' not found in {target_file}.")
    if source_col not in df_source.columns:
        raise ValueError(f"Source column '{source_col}' not found in {source_file}.")

    # Original display values: NaN/blank cells become "" (not the string "nan")
    target_original = df_target[target_col].apply(to_display_string).tolist()
    source_original = df_source[source_col].apply(to_display_string).tolist()

    # Values used for scoring only
    target_processed = [preprocess_text(v, **opts) for v in target_original]
    source_processed = [preprocess_text(v, **opts) for v in source_original]

    if workers is None:
        workers = max(1, mp.cpu_count() - 1)

    n_targets = len(target_processed)
    results = []

    batch_ranges = range(0, n_targets, batch_size)
    iterator = tqdm(batch_ranges, desc="Matching", unit="batch") if tqdm is not None else batch_ranges

    for start in iterator:
        end = min(start + batch_size, n_targets)
        batch_processed = target_processed[start:end]
        batch_original = target_original[start:end]

        # (batch_size x n_source) similarity matrix, computed in C, multi-threaded
        score_matrix = _score_matrix(batch_processed, source_processed, scorer, workers)

        for row_idx in range(score_matrix.shape[0]):
            row_scores = score_matrix[row_idx]
            above_mask = row_scores >= threshold
            above_indices = np.where(above_mask)[0]

            if above_indices.size > 0:
                # Sort qualifying matches by score, descending
                order = above_indices[np.argsort(-row_scores[above_indices])]
                best_idx = order[0]
                best_score = float(row_scores[best_idx])
                best_match = source_original[best_idx]
                all_matches = ', '.join(source_original[i] for i in order)
            else:
                best_score = None
                best_match = None
                all_matches = ''

            results.append({
                'Target_Value': batch_original[row_idx],
                'Best_Match': best_match,
                'Match_Score': best_score,
                'All_Matches_Above_Threshold': all_matches,
            })

    result_df = pd.DataFrame(results)

    # Coerce to numeric before rounding — if EVERY row is a no-match, the
    # column is all None/object dtype and a plain .round() would crash.
    result_df['Match_Score'] = pd.to_numeric(result_df['Match_Score'], errors='coerce').round(2)

    if output_file:
        if output_file.endswith('.csv'):
            result_df.to_csv(output_file, index=False)
        elif output_file.endswith(('.xlsx', '.xls')):
            result_df.to_excel(output_file, index=False, engine='openpyxl')
        else:
            raise ValueError("Output file must end with .csv, .xlsx, or .xls.")

    return result_df


# ----------------------------------------------------------------------
# Example usage (function-call interface only, per agreed spec — no CLI)
# ----------------------------------------------------------------------
if __name__ == "__main__":
    # result_df = fuzzy_match(
    #     target_file="target.csv",
    #     source_file="source.csv",
    #     target_col="name",
    #     source_col="company_name",
    #     scorer="smart",                 # or 'ratio' / 'partial_ratio' / 'token_sort_ratio' / 'token_set_ratio' / 'WRatio'
    #     threshold=80.0,
    #     preprocess_options={"lowercase": True, "trim": True, "remove_punct": True},
    #     workers=-1,                     # -1 = use all CPU cores
    #     batch_size=500,
    #     output_file="result.xlsx",
    # )
    # print(result_df.head())
    pass
