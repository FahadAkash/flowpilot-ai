"""Deterministic 384-dim semantic feature-hash embeddings + cosine similarity.

Provides instant zero-network normalized embeddings suitable for pgvector cosine
indexing and offline tests, while supporting optional external embedding APIs.
"""

from __future__ import annotations

import hashlib
import math
import re

TOKEN_RE = re.compile(r"[a-z0-9]{2,}", re.IGNORECASE)


def embed_text(text: str, *, dim: int = 384) -> list[float]:
    """Compute a deterministic L2-normalized 384-dim semantic feature-hash embedding."""
    vec = [0.0] * dim
    tokens = TOKEN_RE.findall(text.lower())
    if not tokens:
        return vec

    features: list[tuple[str, float]] = []
    for tok in tokens:
        features.append((tok, 1.0))
        if len(tok) >= 4:
            for i in range(len(tok) - 2):
                features.append((f"tri:{tok[i : i + 3]}", 0.35))
    for i in range(len(tokens) - 1):
        features.append((f"bi:{tokens[i]}_{tokens[i + 1]}", 0.8))

    for feat, weight in features:
        digest = hashlib.blake2b(feat.encode("utf-8"), digest_size=8).digest()
        idx = int.from_bytes(digest[:4], "little") % dim
        sign = 1.0 if (digest[4] & 1) == 0 else -1.0
        vec[idx] += sign * weight

    norm = math.sqrt(sum(v * v for v in vec))
    if norm > 0.0:
        vec = [round(v / norm, 6) for v in vec]
    return vec


def cosine_similarity(a: list[float] | None, b: list[float] | None) -> float:
    """Compute cosine similarity between two equal-length vectors."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return float(dot / (na * nb))


def lexical_overlap_score(query: str, text: str) -> float:
    """Compute normalized token overlap score for hybrid retrieval reranking."""
    q_tokens = set(TOKEN_RE.findall(query.lower()))
    if not q_tokens:
        return 0.0
    t_tokens = set(TOKEN_RE.findall(text.lower()))
    if not t_tokens:
        return 0.0
    overlap = len(q_tokens & t_tokens)
    return overlap / len(q_tokens)
