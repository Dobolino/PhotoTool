"""Inhalts-Cluster: ähnliche Motive (Embeddings) → nur die besten behalten."""

from __future__ import annotations

from collections import defaultdict
from datetime import timedelta

import numpy as np
from tqdm import tqdm

from .models import Photo
from .quality import compute_technical_score


def mark_content_clusters(
    photos: list[Photo],
    embeddings: dict[int, np.ndarray],
    *,
    similarity: float = 0.92,
    max_hours: float = 6.0,
    keep_per_cluster: int = 1,
) -> int:
    """
    Gruppiert inhaltsähnliche Fotos (nicht nur pHash-Duplikate).
    Behält die besten `keep_per_cluster` je Cluster, Rest: is_duplicate + content_cluster.
    Returns: Anzahl neu markierter Duplikate.
    """
    indices = [
        i
        for i, p in enumerate(photos)
        if i in embeddings
        and not p.is_duplicate
        and not p.is_burst_reject
        and not getattr(p, "is_aside", False)
        and "unreadable" not in p.flags
    ]
    if len(indices) < 2:
        return 0

    parent = {i: i for i in indices}

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    # Vektoren nur einmal validieren/normalisieren. Histogramm-Fallbacks und
    # Modellvektoren verschiedener Dimensionen niemals miteinander vergleichen.
    vectors: dict[int, np.ndarray] = {}
    by_dimension: dict[int, list[int]] = defaultdict(list)
    for i in indices:
        vec = np.asarray(embeddings[i], dtype=np.float32)
        if vec.ndim != 1 or not vec.size or not np.isfinite(vec).all():
            continue
        norm = float(np.linalg.norm(vec))
        if norm <= 0 or not np.isfinite(norm):
            continue
        vectors[i] = vec / norm
        by_dimension[vec.size].append(i)

    window = timedelta(hours=max_hours)
    for compatible in by_dimension.values():
        matrix = np.stack([vectors[i] for i in compatible])
        for pos, i in enumerate(tqdm(compatible, desc="Inhalts-Cluster", unit="img", leave=False)):
            pi = photos[i]
            positions = []
            for other_pos in range(pos + 1, len(compatible)):
                j = compatible[other_pos]
                pj = photos[j]
                if pi.datetime_taken and pj.datetime_taken:
                    if abs(pi.datetime_taken - pj.datetime_taken) > window:
                        continue
                positions.append(other_pos)
            if not positions:
                continue
            # Ein vektorisierter Vergleich je Foto, ohne eine N×N-Matrix zu halten.
            similarities = np.einsum("ij,j->i", matrix[positions], matrix[pos])
            for offset in np.flatnonzero(similarities >= similarity):
                union(i, compatible[positions[int(offset)]])

    clusters: dict[int, list[int]] = defaultdict(list)
    for i in indices:
        clusters[find(i)].append(i)

    marked = 0
    next_id = 1
    for members in clusters.values():
        if len(members) < 2:
            continue
        members.sort(
            key=lambda i: (
                photos[i].final_score or photos[i].technical_score,
                photos[i].aesthetic_score or 0.0,
            ),
            reverse=True,
        )
        keep = set(members[: max(1, keep_per_cluster)])
        cid = next_id
        next_id += 1
        for i in members:
            photos[i].content_cluster_id = cid
            if i in keep:
                continue
            if photos[i].is_duplicate:
                continue
            photos[i].is_duplicate = True
            photos[i].add_flag("content_duplicate")
            photos[i].duplicate_of = photos[members[0]].filename
            compute_technical_score(photos[i])
            marked += 1
    return marked
