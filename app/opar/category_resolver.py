from __future__ import annotations

import re
from typing import Any, Iterable, Mapping


_DEFAULT_STOPWORDS = {
    "what", "is", "the", "my", "for", "of", "and", "in", "on", "to", "me",
    "show", "give", "please", "spend", "spends", "category", "categories",
    "total", "how", "much", "do", "we", "our", "tell", "about", "optimize",
    "optimise", "optimization", "opportunity", "opportunities", "savings",
    "can", "you",
}


def tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", (text or "").lower())


def match_category_from_query(
    query: str,
    categories: Iterable[Mapping[str, Any]],
    *,
    name_key: str = "category_name",
    id_key: str = "category_id",
    stopwords: set[str] | None = None,
) -> dict[str, Any] | None:
    """Best-effort category matcher using exact phrase and token overlap."""
    lowered = (query or "").lower()
    query_tokens = set(tokenize(lowered))
    if not query_tokens:
        return None
    ignored = _DEFAULT_STOPWORDS if stopwords is None else stopwords
    query_tokens = {token for token in query_tokens if token not in ignored}
    if not query_tokens:
        return None

    best: tuple[int, int, Mapping[str, Any] | None] = (0, 0, None)
    for category in categories:
        cat_name = str(category.get(name_key) or "").lower()
        cat_id = str(category.get(id_key) or "").lower().replace("_", " ")
        blob = f"{cat_name} {cat_id}".strip()
        if not blob:
            continue
        exact = int(bool(cat_name and cat_name in lowered) or bool(cat_id and cat_id in lowered))
        overlap = len(query_tokens.intersection(set(tokenize(blob))))
        score = exact * 10 + overlap
        if score > best[0] or (score == best[0] and overlap > best[1]):
            best = (score, overlap, category)
    return dict(best[2]) if best[0] > 0 and best[2] is not None else None
