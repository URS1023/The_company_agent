from __future__ import annotations

import asyncio
import json
import logging
import socket
from typing import Any

from sqlalchemy import select

from backend.app.core.config import settings
from backend.app.core.database import SessionLocal
from backend.app.core.external_services import redis_client
from backend.app.core.ids import new_id
from backend.app.core.logging import configure_logging
from backend.app.core.security import utc_now
from backend.app.core.storage import LocalFileStorage
from backend.app.models.files import FileAsset
from backend.app.models.knowledge import KnowledgeChunk, KnowledgeDocument
from backend.app.processors.documents import chunk_text, parse_document
from backend.app.providers.compatible import siliconflow_client
from backend.app.providers.elastic_vector import ElasticsearchVectorStore

logger = logging.getLogger(__name__)


async def ingest_document(document_id: str) -> None:
    async with SessionLocal() as db:
        document = await db.get(KnowledgeDocument, document_id)
        if not document:
            return
        file_asset = await db.get(FileAsset, document.file_id)
        if not file_asset:
            document.status = "failed"
            document.error_summary = "源文件不存在"
            document.updated_at = utc_now()
            await db.commit()
            return
        try:
            raw = LocalFileStorage().get_bytes(file_asset.storage_key)
            parsed = parse_document(raw, file_asset.name, file_asset.mime_type)
            chunks = chunk_text(parsed.text)
            if not chunks:
                document.status = "failed"
                document.error_summary = "文件没有可索引文本"
                document.updated_at = utc_now()
                await db.commit()
                return
            for ordinal, chunk_value in enumerate(chunks):
                db.add(
                    KnowledgeChunk(
                        id=new_id(),
                        workspace_id=document.workspace_id,
                        knowledge_base_id=document.knowledge_base_id,
                        document_id=document.id,
                        ordinal=ordinal,
                        text=chunk_value,
                        location={"ordinal": ordinal},
                        embedding_status="pending",
                        created_at=utc_now(),
                    )
                )
            document.status = "awaiting_embedding"
            document.updated_at = utc_now()
            await db.commit()
        except Exception as exc:
            logger.exception("knowledge ingestion failed document_id=%s", document_id)
            document.status = "failed"
            document.error_summary = type(exc).__name__
            document.updated_at = utc_now()
            await db.commit()
            return

        if settings.allow_external_embedding and settings.siliconflow_api_key:
            await embed_document(document_id)


async def embed_document(document_id: str) -> None:
    async with SessionLocal() as db:
        document = await db.get(KnowledgeDocument, document_id)
        if not document:
            return
        chunks = list(
            await db.scalars(
                select(KnowledgeChunk)
                .where(KnowledgeChunk.document_id == document.id)
                .order_by(KnowledgeChunk.ordinal)
            )
        )
        if not chunks:
            return
        vectors = await siliconflow_client().embeddings(
            model=settings.siliconflow_embedding_model,
            inputs=[chunk.text for chunk in chunks],
        )
        if any(len(vector) != settings.siliconflow_embedding_dimensions for vector in vectors):
            raise ValueError("embedding dimension does not match configured Elasticsearch mapping")
        vector_store = ElasticsearchVectorStore()
        await vector_store.ensure_index()
        for chunk, vector in zip(chunks, vectors, strict=True):
            await vector_store.upsert_chunk(
                chunk.id,
                {
                    "workspace_id": chunk.workspace_id,
                    "knowledge_base_id": chunk.knowledge_base_id,
                    "document_version_id": chunk.document_id,
                    "chunk_id": chunk.id,
                    "content": chunk.text,
                    "location": chunk.location,
                    "embedding": vector,
                },
            )
            chunk.embedding_status = "indexed"
            chunk.embedding_model = settings.siliconflow_embedding_model
            chunk.embedding_dimensions = len(vector)
            chunk.elasticsearch_document_id = chunk.id
        document.status = "ready"
        document.updated_at = utc_now()
        await db.commit()


async def ensure_group(client: Any) -> None:
    try:
        await client.xgroup_create(
            settings.redis_stream_name,
            f"{settings.redis_consumer_group}-ingestion",
            id="0",
            mkstream=True,
        )
    except Exception as exc:
        if "BUSYGROUP" not in str(exc):
            raise


async def run_forever() -> None:
    group = f"{settings.redis_consumer_group}-ingestion"
    consumer = f"{socket.gethostname()}-{id(asyncio.current_task())}"
    client = redis_client()
    await ensure_group(client)
    try:
        while True:
            messages = await client.xreadgroup(
                groupname=group,
                consumername=consumer,
                streams={settings.redis_stream_name: ">"},
                count=1,
                block=1000,
            )
            for _, entries in messages:
                for message_id, values in entries:
                    try:
                        payload = json.loads(values.get("payload", "{}"))
                        if values.get("topic") == "knowledge.document.created" and payload.get(
                            "document_id"
                        ):
                            await ingest_document(payload["document_id"])
                        await client.xack(settings.redis_stream_name, group, message_id)
                    except Exception:
                        logger.exception("ingestion event failed id=%s", message_id)
    finally:
        await client.aclose()


def main() -> None:
    configure_logging()
    asyncio.run(run_forever())


if __name__ == "__main__":
    main()
