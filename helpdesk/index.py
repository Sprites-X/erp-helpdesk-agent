"""Vector store (Chroma) — สร้าง index และค้นหาแบบกรองตามโมดูลได้"""
from functools import lru_cache

import chromadb

from . import config
from .llm import embed


@lru_cache(maxsize=1)
def _client():
    config.CHROMA_DIR.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=str(config.CHROMA_DIR))


def build_index(chunks: list[dict]) -> int:
    client = _client()
    try:
        client.delete_collection(config.COLLECTION)
    except Exception:
        pass
    col = client.create_collection(
        config.COLLECTION,
        metadata={"hnsw:space": "cosine", "backend": config.BACKEND, "embed_model": config.EMBED_MODEL},
        embedding_function=None,
    )
    vectors = embed([c["text"] for c in chunks])
    col.add(
        ids=[c["id"] for c in chunks],
        documents=[c["text"] for c in chunks],
        embeddings=vectors,
        metadatas=[{k: c[k] for k in ("module", "title", "source", "doc_type")} for c in chunks],
    )
    return col.count()


@lru_cache(maxsize=1)
def _collection():
    try:
        col = _client().get_collection(config.COLLECTION, embedding_function=None)
    except Exception as e:
        raise RuntimeError("ยังไม่มี index — รัน `python prep.py` ก่อน") from e
    built_with = (col.metadata or {}).get("backend")
    if built_with and built_with != config.BACKEND:
        raise RuntimeError(f"index สร้างด้วย backend '{built_with}' แต่ตอนนี้ใช้ '{config.BACKEND}' — รัน `python prep.py` ใหม่")
    return col


def search(query: str, module: str | None = None, k: int = config.TOP_K) -> list[dict]:
    """ค้น top-k ถ้าระบุ module จะค้นเฉพาะโมดูลนั้น + GENERAL"""
    col = _collection()
    where = {"module": {"$in": [module, "GENERAL"]}} if module and module not in ("GENERAL", "UNKNOWN") else None
    res = col.query(query_embeddings=embed([query]), n_results=k, where=where)
    hits = []
    for cid, doc, meta, dist in zip(res["ids"][0], res["documents"][0], res["metadatas"][0], res["distances"][0]):
        hits.append({"id": cid, "score": round(1 - dist, 4), "text": doc, **meta})
    return hits
