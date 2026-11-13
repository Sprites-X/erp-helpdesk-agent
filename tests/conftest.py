"""ของที่ใช้ร่วมกันในชุดทดสอบ

ทดสอบทั้งหมดรันได้โดยไม่ต้องมี GPU หรือ Ollama:
  - FakeOllama แทนที่ llm._post ตอบตาม JSON schema ที่แต่ละ agent ส่งมา จึงทดสอบโค้ดจริงของ agent ได้ทั้งเส้น
    (สร้าง prompt → เรียกโมเดล → parse JSON → ตรวจหลักฐาน → บันทึกสถิติ)
  - fake_search แทนที่การค้นใน vector store ให้กำหนดได้ว่าแต่ละคำค้นเจอเอกสารอะไร คะแนนเท่าไร
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from helpdesk import config, graph, llm  # noqa: E402
from helpdesk.llm import LLMError  # noqa: E402


def doc(doc_id: str, text: str, score: float, module: str | None = None, title: str = "") -> dict:
    """สร้างผลการค้น 1 รายการในรูปแบบเดียวกับ index.search"""
    module = module or doc_id.split("-")[0]
    return {"id": doc_id, "score": score, "text": text, "module": module,
            "title": title or doc_id, "source": "test", "doc_type": "manual"}


class FakeOllama:
    """แทน Ollama: ดูจาก field ใน schema ว่าเป็นคำขอของ agent ไหน แล้วตอบค่าที่กำหนดไว้

    ค่าที่กำหนดเป็น dict, ฟังก์ชันที่รับข้อความ user แล้วคืน dict, หรือ exception ที่จะถูก raise ก็ได้
    """
    KINDS = {"rewritten_query": "router", "evidence": "evidence", "retry": "retry", "priority": "ticket"}

    def __init__(self):
        self.replies = {
            "router": {"intent": "how_to", "module": "PO", "rewritten_query": ""},
            "evidence": {"evidence": "", "doc_id": "", "answer": ""},
            "retry": {"retry": False, "new_query": ""},
            "ticket": {"title": "ปัญหาทดสอบ", "priority": "high", "summary": "สรุป", "info_needed": ["ภาพหน้าจอ"]},
        }
        self.calls: list[str] = []

    def kind(self, schema: dict) -> str:
        for key, kind in self.KINDS.items():
            if key in schema["properties"]:
                return kind
        raise AssertionError(f"schema ที่ไม่รู้จัก: {schema}")

    def __call__(self, path: str, payload: dict, timeout: int = 180) -> dict:
        assert path == "/api/chat", path
        kind = self.kind(payload["format"])
        self.calls.append(kind)
        reply = self.replies[kind]
        if isinstance(reply, Exception):
            raise reply
        if callable(reply):
            reply = reply(payload["messages"][1]["content"])
        return {"message": {"role": "assistant", "content": json.dumps(reply, ensure_ascii=False)},
                "prompt_eval_count": 800, "prompt_eval_duration": 300_000_000,
                "eval_count": 40, "eval_duration": 900_000_000, "load_duration": 0}


@pytest.fixture
def fake_ollama(monkeypatch, tmp_path):
    """ให้ระบบทำงานแบบ backend=ollama แต่ไม่ต่อ Ollama จริง และไม่เขียน ticket ลงโฟลเดอร์ของโปรเจกต์"""
    fake = FakeOllama()
    monkeypatch.setattr(config, "BACKEND", "ollama")
    monkeypatch.setattr(config, "MIN_SCORE", 0.55)
    monkeypatch.setattr(config, "SCOPE_RESCUE_SCORE", 0.55)
    monkeypatch.setattr(config, "MAX_EXTRA_SEARCHES", 1)
    monkeypatch.setattr(config, "TICKET_DIR", tmp_path / "tickets")
    monkeypatch.setattr(llm, "_post", fake)
    llm.take_calls()
    return fake


@pytest.fixture
def fake_search(monkeypatch):
    """กำหนดผลการค้น: kb.results[คำค้น] = รายการเอกสาร ถ้าไม่กำหนดจะใช้ kb.default

    เก็บทุกการค้นไว้ใน kb.queries เพื่อตรวจว่าระบบค้นด้วยคำอะไร กี่ครั้ง
    """
    class KB:
        def __init__(self):
            self.results: dict[str, list[dict]] = {}
            self.default: list[dict] = []
            self.queries: list[tuple[str, str | None]] = []

        def __call__(self, query: str, module: str | None = None, k: int = 4) -> list[dict]:
            self.queries.append((query, module))
            hits = self.results.get(query, self.default)
            return sorted(hits, key=lambda h: h["score"], reverse=True)[:k]

    kb = KB()
    monkeypatch.setattr(graph, "search", kb)
    return kb


__all__ = ["doc", "FakeOllama", "LLMError"]
