from __future__ import annotations

import hashlib
import math

EMBEDDING_DIMENSION = 256
DEFAULT_EMBEDDING_MODEL = "stub-hash-v1"


class StubEmbeddingProvider:
    def __init__(self, model: str = DEFAULT_EMBEDDING_MODEL) -> None:
        self.model = model

    def embed(self, text: str) -> list[float]:
        values: list[float] = []
        seed = text.strip().lower().encode()
        counter = 0
        while len(values) < EMBEDDING_DIMENSION:
            digest = hashlib.sha256(seed + counter.to_bytes(4, "big")).digest()
            values.extend(((byte / 127.5) - 1.0) for byte in digest)
            counter += 1
        vector = values[:EMBEDDING_DIMENSION]
        magnitude = math.sqrt(sum(component * component for component in vector))
        if magnitude == 0:
            return [0.0] * EMBEDDING_DIMENSION
        return [component / magnitude for component in vector]


def vector_literal(vector: list[float]) -> str:
    if len(vector) != EMBEDDING_DIMENSION:
        raise ValueError("embedding vector must have 256 components")
    return "[" + ",".join(f"{component:.8f}" for component in vector) + "]"
