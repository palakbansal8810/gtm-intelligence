import time
import hashlib
import numpy as np
from dataclasses import dataclass, field
import faiss

EMBED_DIM = 128 


def _pseudo_embed(text: str, dim: int = EMBED_DIM) -> np.ndarray:

    tokens = text.lower().split()
    vec = np.zeros(dim, dtype=np.float32)
    for i, tok in enumerate(tokens):
        h = int(hashlib.md5(tok.encode()).hexdigest(), 16)
        idx = h % dim
        vec[idx] += 1.0 / (i + 1)
    norm = np.linalg.norm(vec)
    if norm > 0:
        vec /= norm
    return vec


@dataclass
class MemoryEntry:
    id: str
    query: str
    plan: dict
    results: list
    signals: list
    gtm_strategy: dict
    confidence: float
    timestamp: float = field(default_factory=time.time)


class VectorMemory:

    def __init__(self, dim: int = EMBED_DIM, max_entries: int = 500):
        self.dim = dim
        self.max_entries = max_entries
        self._entries: list[MemoryEntry] = []
        self._vectors: list[np.ndarray] = []

        self._index = faiss.IndexFlatIP(dim)  

    def store(self,query: str,plan: dict,results: list,signals: list,gtm_strategy: dict,confidence: float,) -> str:
        
        entry_id = hashlib.md5(f"{query}{time.time()}".encode()).hexdigest()[:12]
        entry = MemoryEntry(
            id=entry_id,
            query=query,
            plan=plan,
            results=results,
            signals=signals,
            gtm_strategy=gtm_strategy,
            confidence=confidence,
        )
        vec = _pseudo_embed(query, self.dim)

        self._entries.append(entry)
        self._vectors.append(vec)

        if self._index is not None:
            self._index.add(vec.reshape(1, -1))

        if len(self._entries) > self.max_entries:
            self._entries.pop(0)
            self._vectors.pop(0)
            if self._index is not None:
                self._index = faiss.IndexFlatIP(self.dim)
                vecs = np.array(self._vectors, dtype=np.float32)
                self._index.add(vecs)

        return entry_id

    def retrieve(self, query: str, top_k: int = 3, threshold: float = 0.7) -> list[dict]:
        """Return top-k similar past entries above similarity threshold."""
        if not self._entries:
            return []

        query_vec = _pseudo_embed(query, self.dim).reshape(1, -1)

        if self._index is not None and len(self._entries) > 0:
            k = min(top_k, len(self._entries))
            scores, indices = self._index.search(query_vec, k)
            hits = []
            for score, idx in zip(scores[0], indices[0]):
                if idx >= 0 and score >= threshold:
                    e = self._entries[idx]
                    hits.append({"similarity": float(score), "entry": self._entry_to_dict(e)})
            return hits
        else:
     
            scores = []
            for i, vec in enumerate(self._vectors):
                sim = float(np.dot(query_vec[0], vec))
                scores.append((sim, i))
            scores.sort(reverse=True)
            hits = []
            for sim, idx in scores[:top_k]:
                if sim >= threshold:
                    e = self._entries[idx]
                    hits.append({"similarity": sim, "entry": self._entry_to_dict(e)})
            return hits

    def get_all_ids(self) -> list[str]:
        return [e.id for e in self._entries]

    def _entry_to_dict(self, e: MemoryEntry) -> dict:
        return {
            "id": e.id,
            "query": e.query,
            "plan": e.plan,
            "results": e.results,
            "signals": e.signals,
            "gtm_strategy": e.gtm_strategy,
            "confidence": e.confidence,
            "timestamp": e.timestamp,
        }

    def summary(self) -> dict:
        return {
            "total_entries": len(self._entries),
            "dim": self.dim,
        }

memory_store = VectorMemory()