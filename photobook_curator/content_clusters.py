"""Inhalts-Cluster: ähnliche Motive (Embeddings) → nur die besten behalten."""

from __future__ import annotations

from collections import defaultdict
from datetime import timedelta

import numpy as np
from tqdm import tqdm

from .embeddings import cosine_similarity
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

    window = timedelta(hours=max_hours)
    for pos, i in enumerate(tqdm(indices, desc="Inhalts-Cluster", unit="img", leave=False)):
        pi = photos[i]
        ei = embeddings[i]
        for j in indices[pos + 1 :]:
            pj = photos[j]
            if pi.datetime_taken and pj.datetime_taken:
                if abs(pi.datetime_taken - pj.datetime_taken) > window:
                    continue
            sim = cosine_similarity(ei, embeddings[j])
            if sim >= similarity:
                union(i, j)

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
