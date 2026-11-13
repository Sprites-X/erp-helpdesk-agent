"""ทดสอบ vector store จริง (Chroma) ด้วย embedding แบบ stub บนข้อมูลจริงของโปรเจกต์"""
import pytest

from helpdesk import config, graph, index
from helpdesk.prep.chunk import chunk_manual
from helpdesk.prep.clean import clean_text
from helpdesk.prep.faq import load_faq


@pytest.fixture
def stub_index(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "BACKEND", "stub")
    monkeypatch.setattr(config, "CHROMA_DIR", tmp_path / "chroma")
    monkeypatch.setattr(config, "TICKET_DIR", tmp_path / "tickets")
    index._client.cache_clear()
    index._collection.cache_clear()
    chunks = []
    for path in sorted(config.RAW_DIR.glob("manual_*.txt")):
        cleaned, _ = clean_text(path.read_text(encoding="utf-8"))
        chunks += chunk_manual(cleaned, path.stem.split("_", 1)[1].upper(), path.name)
    chunks += load_faq(config.RAW_DIR / "faq_export.csv")[0]
    count = index.build_index(chunks)
    yield chunks, count
    index._client.cache_clear()
    index._collection.cache_clear()


def test_every_chunk_is_indexed(stub_index):
    chunks, count = stub_index
    assert count == len(chunks) >= 30
    assert len({c["id"] for c in chunks}) == len(chunks)


def test_module_filter_keeps_module_and_general(stub_index):
    hits = index.search("ตั้งหนี้ใบแจ้งหนี้", "AP", k=6)
    assert hits and {h["module"] for h in hits} <= {"AP", "GENERAL"}
    assert hits == sorted(hits, key=lambda h: h["score"], reverse=True)


def test_index_built_by_another_backend_is_rejected(stub_index, monkeypatch):
    # สร้างด้วย stub แล้วจะเอาไปใช้กับ Ollama ไม่ได้ เพราะ embedding คนละแบบ ค้นแล้วได้ขยะ
    monkeypatch.setattr(config, "BACKEND", "ollama")
    index._collection.cache_clear()
    with pytest.raises(RuntimeError, match="prep.py"):
        index.search("อะไรก็ได้")


def test_stub_pipeline_runs_end_to_end(stub_index):
    state = graph.run("PO อนุมัติแล้วแก้ไขยังไง", save_ticket=False)
    assert state["outcome"] in {"answer", "ticket"}
    assert [t["agent"] for t in state["trace"]][:2] == ["Router", "Retriever"]
    assert graph.run("พรุ่งนี้ฝนตกไหม", save_ticket=False)["outcome"] == "out_of_scope"
