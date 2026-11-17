"""Comparación de títulos y puntuación de candidatos."""
from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher
from typing import Iterable

__all__ = ["normalize", "similarity", "score_candidate"]

_LEADING_ARTICLES = frozenset({"the", "a", "an", "el", "la", "los", "las", "un", "una"})


def normalize(text: str) -> str:
    """Minúsculas, sin acentos ni signos, y sin artículo inicial: «¡El Señor!» -> «senor»."""
    s = unicodedata.normalize("NFKD", text)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.casefold().replace("&", " and ")
    s = re.sub(r"[\W_]+", " ", s)
    words = s.split()
    if len(words) > 1 and words[0] in _LEADING_ARTICLES:
        words = words[1:]
    return " ".join(words)


def similarity(a: str, b: str) -> float:
    """Parecido entre dos títulos, de 0 a 1 (1 = iguales tras normalizar)."""
    na, nb = normalize(a), normalize(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    direct = SequenceMatcher(None, na, nb).ratio()
    # Tolera el orden de palabras cambiado.
    token = SequenceMatcher(None, " ".join(sorted(na.split())), " ".join(sorted(nb.split()))).ratio()
    return max(direct, token * 0.95)


def score_candidate(
    query: str,
    query_year: int | None,
    titles: Iterable[str],
    candidate_year: int | None,
    popularity: float = 0.0,
) -> float:
    """Puntuación de un candidato: parecido del título + año + un toque de popularidad.

    ``titles`` son los nombres del candidato (traducido y original): se usa el mejor.
    """
    base = max((similarity(query, t) for t in titles if t), default=0.0)
    bonus = 0.0
    if query_year and candidate_year:
        diff = abs(query_year - candidate_year)
        bonus += 0.15 if diff == 0 else 0.05 if diff == 1 else -0.15
    bonus += min(max(popularity, 0.0), 100.0) / 100.0 * 0.05  # solo desempata
    return round(base + bonus, 4)
