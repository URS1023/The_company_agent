from __future__ import annotations

from typing import Any

from backend.app.core.config import settings
from backend.app.core.external_services import elasticsearch_client


class VectorStoreError(RuntimeError):
    pass


class ElasticsearchVectorStore:
    """Elasticsearch dense-vector adapter for native development."""

    def __init__(self, client: Any | None = None) -> None:
        self._client = client

    async def _get_client(self) -> Any:
        if self._client is None:
            self._client = elasticsearch_client()
        return self._client

    @property
    def index_name(self) -> str:
        return f"{settings.elasticsearch_index_prefix}-v1-bge-m3-1024"

    async def ensure_index(self) -> None:
        client = await self._get_client()
        if await client.indices.exists(index=self.index_name):
            return
        await client.indices.create(
            index=self.index_name,
            mappings={
                "properties": {
                    "workspace_id": {"type": "keyword"},
                    "knowledge_base_id": {"type": "keyword"},
                    "document_version_id": {"type": "keyword"},
                    "chunk_id": {"type": "keyword"},
                    "content": {"type": "text"},
                    "location": {"type": "object", "enabled": True},
                    "embedding": {
                        "type": "dense_vector",
                        "dims": settings.siliconflow_embedding_dimensions,
                        "index": True,
                        "similarity": "cosine",
                    },
                }
            },
        )

    async def upsert_chunk(self, chunk_id: str, document: dict[str, Any]) -> None:
        client = await self._get_client()
        await client.index(
            index=self.index_name, id=chunk_id, document=document, refresh="wait_for"
        )

    async def search(
        self,
        *,
        workspace_id: str,
        knowledge_base_id: str,
        query_vector: list[float],
        k: int = 8,
    ) -> list[dict[str, Any]]:
        client = await self._get_client()
        response = await client.search(
            index=self.index_name,
            knn={
                "field": "embedding",
                "query_vector": query_vector,
                "k": k,
                "num_candidates": max(50, k * 8),
                "filter": [
                    {"term": {"workspace_id": workspace_id}},
                    {"term": {"knowledge_base_id": knowledge_base_id}},
                ],
            },
        )
        return [
            hit.get("_source", {}) | {"score": hit.get("_score")}
            for hit in response["hits"]["hits"]
        ]


__all__ = ["ElasticsearchVectorStore", "VectorStoreError"]
