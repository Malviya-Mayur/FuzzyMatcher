#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Fuzzy Matcher - offline fuzzy text matching between two columns from CSV/XLSX files.
Version: 3.0  - async-ready, TF-IDF blocking, plugin scorers, unicode normalization
"""

import re
import os
import warnings
import unicodedata
import importlib.util
from pathlib import Path
from typing import Optional, Dict, List, Callable

import numpy as np
import pandas as pd
from rapidfuzz import fuzz, process

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

try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
    _SKLEARN_AVAILABLE = True
except ImportError:
    _SKLEARN_AVAILABLE = False
    warnings.warn("scikit-learn not installed; TF-IDF blocking disabled.", UserWarning)

try:
    import psutil
    _PSUTIL_AVAILABLE = True
except ImportError:
    _PSUTIL_AVAILABLE = False

STOPWORDS = {
    "a","about","above","after","again","against","all","am","an","and",
    "any","are","as","at","be","because","been","before","being","below",
    "between","both","but","by","could","did","do","does","doing","down",
    "during","each","few","for","from","further","had","has","have","having",
    "he","her","here","hers","herself","him","himself","his","how","i","if",
    "in","into","is","it","its","itself","me","more","most","my","myself",
    "nor","of","on","once","only","or","other","our","ours","ourselves","out",
    "over","own","same","she","should","so","some","such","than","that","the",
    "their","theirs","them","themselves","then","there","these","they","this",
    "those","through","to","too","under","until","up","very","was","we","were",
    "what","when","where","which","while","who","whom","why","with","would",
    "you","your","yours","yourself","yourselves",
    "ltd","limited","inc","incorporated","corp","corporation","co","company",
    "llc","llp","plc","gmbh","ag","sa","bv","nv","pty","pvt","srl","spa",
    "aps","ab","oy","sas","sarl",
}

_PLUGIN_SCORERS: Dict[str, Callable[[str, str], float]] = {}


def load_plugin_scorers(scorers_dir: Optional[str] = None) -> Dict[str, str]:
    global _PLUGIN_SCORERS
    if scorers_dir is None:
        scorers_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scorers")
    loaded: Dict[str, str] = {}
    if not os.path.isdir(scorers_dir):
        return loaded
    for fpath in Path(scorers_dir).glob("*.py"):
        if fpath.name.startswith("_"):
            continue
        try:
            spec = importlib.util.spec_from_file_location(f"scorer_{fpath.stem}", fpath)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            if hasattr(mod, "NAME") and hasattr(mod, "score") and callable(mod.score):
                key = f"plugin_{fpath.stem}"
                _PLUGIN_SCORERS[key] = mod.score
                loaded[key] = mod.NAME
        except Exception as e:
            warnings.warn(f"Failed to load scorer plugin {fpath.name}: {e}", UserWarning)
    return loaded


def get_all_scorer_names() -> Dict[str, str]:
    built_ins = {
        "smart":            "Smart (Ensemble)",
        "ratio":            "Ratio",
        "partial_ratio":    "Partial Ratio",
        "token_sort_ratio": "Token Sort Ratio",
        "token_set_ratio":  "Token Set Ratio",
        "WRatio":           "WRatio",
    }
    built_ins.update({k: v for k, v in _PLUGIN_SCORERS.items() if k not in built_ins})
    return built_ins


def strip_invisible(text: str) -> str:
    return re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f\u200b-\u200f\u2028-\u202f]', '', text)


def normalize_unicode(text: str) -> str:
    try:
        return unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('ascii')
    except Exception:
        return text


def to_display_string(value) -> str:
    if pd.isna(value):
        return ''
    return str(value).strip()


def preprocess_text(text: str,
                     lowercase: bool = False,
                     trim: bool = False,
                     remove_punct: bool = False,
                     remove_stopwords: bool = False,
                     stem: bool = False,
                     normalize_accents: bool = True) -> str:
    if not isinstance(text, str):
        text = str(text)
    text = strip_invisible(text)
    if normalize_accents:
        text = normalize_unicode(text)
    if lowercase:
        text = text.lower()
    if remove_punct:
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
            text = ' '.join(_stemmer.stem(w) for w in text.split())
        else:
            warnings.warn("Stemming requested but nltk not installed. Skipping.", UserWarning)
    return text


_SCORER_MAP = {
    "ratio":            fuzz.ratio,
    "partial_ratio":    fuzz.partial_ratio,
    "token_sort_ratio": fuzz.token_sort_ratio,
    "token_set_ratio":  fuzz.token_set_ratio,
    "WRatio":           fuzz.WRatio,
}
_SMART_SCORERS = [fuzz.ratio, fuzz.partial_ratio, fuzz.token_sort_ratio, fuzz.token_set_ratio, fuzz.WRatio]
_SMART_WEIGHTS = np.array([0.20, 0.15, 0.20, 0.15, 0.30], dtype=np.float32)


def _score_matrix(target_batch: List[str], source_list: List[str],
                  scorer: str, workers: int) -> np.ndarray:
    if scorer == "smart":
        mats = [process.cdist(target_batch, source_list, scorer=s,
                               workers=workers, dtype=np.float32)
                for s in _SMART_SCORERS]
        return sum(w * m for w, m in zip(_SMART_WEIGHTS, mats))
    if scorer in _PLUGIN_SCORERS:
        fn = _PLUGIN_SCORERS[scorer]
        mat = np.zeros((len(target_batch), len(source_list)), dtype=np.float32)
        for i, t in enumerate(target_batch):
            for j, s in enumerate(source_list):
                mat[i, j] = fn(t, s)
        return mat
    if scorer not in _SCORER_MAP:
        raise ValueError(f"Unknown scorer: {scorer!r}.")
    return process.cdist(target_batch, source_list, scorer=_SCORER_MAP[scorer],
                         workers=workers, dtype=np.float32)


def _build_tfidf_index(source_processed: List[str]):
    if not _SKLEARN_AVAILABLE or len(source_processed) < 500:
        return None
    try:
        vec = TfidfVectorizer(analyzer='char_wb', ngram_range=(2, 3), min_df=1)
        mat = vec.fit_transform(source_processed)
        return (vec, mat)
    except Exception:
        return None


def _get_candidate_indices(target_batch: List[str], tfidf_index, top_k: int = 50):
    if tfidf_index is None:
        return None
    vec, src_mat = tfidf_index
    try:
        tgt_mat = vec.transform(target_batch)
        sims = cosine_similarity(tgt_mat, src_mat)
        k = min(top_k, src_mat.shape[0])
        return np.argpartition(-sims, k - 1, axis=1)[:, :k].tolist()
    except Exception:
        return None


def _compute_batch_size(n_source: int, n_scorers: int = 1) -> int:
    if _PSUTIL_AVAILABLE:
        target_bytes = int(psutil.virtual_memory().available * 0.20)
    else:
        target_bytes = 512 * 1024 * 1024
    bytes_per_row = n_source * 4 * n_scorers
    if bytes_per_row == 0:
        return 500
    return int(max(50, min(2000, target_bytes // bytes_per_row)))


def _confidence_tier(score) -> str:
    try:
        s = float(score)
        if s >= 90:
            return "High"
        if s >= 70:
            return "Medium"
        return "Low"
    except (TypeError, ValueError):
        return "No Match"


def fuzzy_match(
    target_file: str,
    source_file: str,
    target_col: str,
    source_col: str,
    scorer: str = "smart",
    threshold: float = 80.0,
    preprocess_options: Optional[Dict[str, bool]] = None,
    workers: Optional[int] = None,
    batch_size: Optional[int] = None,
    output_file: Optional[str] = None,
    csv_separator: str = ',',
    csv_quotechar: Optional[str] = '"',
    progress_callback: Optional[Callable[[int, int], None]] = None,
) -> pd.DataFrame:
    if preprocess_options is None:
        preprocess_options = {}
    opts = {
        'lowercase':         preprocess_options.get('lowercase', False),
        'trim':              preprocess_options.get('trim', False),
        'remove_punct':      preprocess_options.get('remove_punct', False),
        'remove_stopwords':  preprocess_options.get('remove_stopwords', False),
        'stem':              preprocess_options.get('stem', False),
        'normalize_accents': preprocess_options.get('normalize_accents', True),
    }

    import multiprocessing as mp

    def load_file(fp: str) -> pd.DataFrame:
        if fp.endswith('.csv'):
            if csv_quotechar == '':
                return pd.read_csv(fp, sep=csv_separator, quoting=3)
            return pd.read_csv(fp, sep=csv_separator, quotechar=csv_quotechar)
        elif fp.endswith(('.xlsx', '.xls')):
            return pd.read_excel(fp, engine='openpyxl')
        raise ValueError(f"Unsupported file format: {fp}")

    df_target = load_file(target_file)
    df_source = load_file(source_file)

    if target_col not in df_target.columns:
        raise ValueError(f"Target column '{target_col}' not found.")
    if source_col not in df_source.columns:
        raise ValueError(f"Source column '{source_col}' not found.")

    target_original = df_target[target_col].apply(to_display_string).tolist()
    source_original_full = df_source[source_col].apply(to_display_string).tolist()

    source_unique, _ = np.unique(source_original_full, return_inverse=True)
    source_original  = source_unique.tolist()

    target_processed = [preprocess_text(v, **opts) for v in target_original]
    source_processed = [preprocess_text(v, **opts) for v in source_original]

    if workers is None:
        workers = max(1, mp.cpu_count() - 1)

    n_scorers      = 5 if scorer == "smart" else 1
    eff_batch      = batch_size or _compute_batch_size(len(source_processed), n_scorers)
    tfidf_index    = _build_tfidf_index(source_processed)
    use_blocking   = tfidf_index is not None

    n_targets     = len(target_processed)
    batch_starts  = list(range(0, n_targets, eff_batch))
    total_batches = len(batch_starts)
    results       = []

    iterator = (tqdm(enumerate(batch_starts), desc="Matching", unit="batch", total=total_batches)
                if tqdm else enumerate(batch_starts))

    for batch_num, start in iterator:
        end             = min(start + eff_batch, n_targets)
        batch_processed = target_processed[start:end]
        batch_original  = target_original[start:end]

        candidate_lists = _get_candidate_indices(batch_processed, tfidf_index) if use_blocking else None

        for row_idx, t_orig in enumerate(batch_original):
            t_proc = [batch_processed[row_idx]]

            if candidate_lists is not None:
                cand_idx     = candidate_lists[row_idx]
                score_row    = _score_matrix(t_proc, [source_processed[i] for i in cand_idx], scorer, workers)[0]
                above_local  = np.where(score_row >= threshold)[0]
                above_global = np.array([cand_idx[i] for i in above_local])
                above_scores = score_row[above_local]
            else:
                score_row    = _score_matrix(t_proc, source_processed, scorer, workers)[0]
                above_global = np.where(score_row >= threshold)[0]
                above_scores = score_row[above_global]

            if above_global.size > 0:
                order       = np.argsort(-above_scores)
                best_score  = float(above_scores[order[0]])
                best_match  = source_original[above_global[order[0]]]
                all_matches = ', '.join(source_original[i] for i in above_global[order])
            else:
                best_score  = None
                best_match  = None
                all_matches = ''

            results.append({
                'Target_Value':                t_orig,
                'Best_Match':                  best_match,
                'Match_Score':                 best_score,
                'Confidence':                  _confidence_tier(best_score),
                'All_Matches_Above_Threshold': all_matches,
            })

        if progress_callback:
            progress_callback(batch_num + 1, total_batches)

    result_df = pd.DataFrame(results)
    result_df['Match_Score'] = pd.to_numeric(result_df['Match_Score'], errors='coerce').round(2)

    if output_file:
        if output_file.endswith('.csv'):
            result_df.to_csv(output_file, index=False)
        elif output_file.endswith(('.xlsx', '.xls')):
            result_df.to_excel(output_file, index=False, engine='openpyxl')
        else:
            raise ValueError("Output file must end with .csv, .xlsx, or .xls.")

    return result_df


if __name__ == "__main__":
    pass