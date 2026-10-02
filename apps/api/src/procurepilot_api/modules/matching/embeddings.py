from __future__ import annotations

import hashlib
import json
import math
import os
from typing import Any

EMBEDDING_DIMENSION = 256
DEFAULT_EMBEDDING_MODEL = "stub-hash-v1"
DEFAULT_BEDROCK_EMBEDDING_MODEL = "amazon.titan-embed-text-v2:0"


class EmbeddingProviderError(RuntimeError):
    """Raised when an embedding provider cannot produce a valid vector."""


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


class BedrockEmbeddingProvider:
    def __init__(self, model: str = DEFAULT_BEDROCK_EMBEDDING_MODEL) -> None:
        self.model = model
        self._aws_region = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
        self._aws_profile = os.environ.get("AWS_PROFILE", "")

    def embed(self, text: str) -> list[float]:
        session_kwargs: dict[str, Any] = {}
        if self._aws_profile:
            session_kwargs["profile_name"] = self._aws_profile
        try:
            import boto3  # noqa: PLC0415 — lazy so stub mode has no boto3 runtime dependency
        except ModuleNotFoundError as exc:
            raise EmbeddingProviderError(
                "boto3 is not installed. Set "
                "MATCHING_EMBEDDING_PROVIDER_MODE=stub for local/test use."
            ) from exc
        try:
            client = boto3.Session(**session_kwargs).client(
                "bedrock-runtime", region_name=self._aws_region
            )
            response = client.invoke_model(
                modelId=self.model,
                body=json.dumps(
                    {"inputText": text, "dimensions": EMBEDDING_DIMENSION, "normalize": True}
                ),
            )
            payload = json.loads(response["body"].read())
            vector = payload["embedding"]
            if not isinstance(vector, list) or len(vector) != EMBEDDING_DIMENSION:
                raise ValueError("Bedrock returned an embedding with an invalid dimension")
            return [float(value) for value in vector]
        except Exception as exc:
            raise EmbeddingProviderError(f"Bedrock embedding failed: {exc}") from exc


def get_embedding_provider(settings: object) -> StubEmbeddingProvider | BedrockEmbeddingProvider:
    mode = getattr(settings, "matching_embedding_provider_mode", "stub")
    model = getattr(settings, "matching_embedding_model", DEFAULT_EMBEDDING_MODEL)
    if mode == "bedrock":
        if model == DEFAULT_EMBEDDING_MODEL:
            model = DEFAULT_BEDROCK_EMBEDDING_MODEL
        return BedrockEmbeddingProvider(model)
    return StubEmbeddingProvider(model)


def vector_literal(vector: list[float]) -> str:
    if len(vector) != EMBEDDING_DIMENSION:
        raise ValueError("embedding vector must have 256 components")
    return "[" + ",".join(f"{component:.8f}" for component in vector) + "]"
