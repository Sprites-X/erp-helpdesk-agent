"""ตรวจชุดคำถามทดสอบทุกไฟล์ใน data/eval ว่าเฉลยสอดคล้องกับคลังความรู้"""
import json

import pytest
from conftest import ROOT

from tools.check_eval_set import check

SETS = sorted((ROOT / "data" / "eval").glob("*.jsonl"))


@pytest.mark.parametrize("path", SETS, ids=[p.name for p in SETS])
def test_eval_set_is_consistent(path):
    items, errors, _ = check(path)
    assert items
    assert errors == []


def test_checker_catches_wrong_answer_key(tmp_path):
    bad = [
        {"id": "x01", "question": "คำถามทดสอบที่ไม่ซ้ำ 1", "intent": "how_to", "module": "PO",
         "outcome": "answer", "expected_sources": ["PO-99"], "must_include": ["อะไรสักอย่าง"]},
        {"id": "x02", "question": "คำถามทดสอบที่ไม่ซ้ำ 2", "intent": "out_of_scope", "module": "PO",
         "outcome": "out_of_scope", "expected_sources": [], "must_include": []},
        {"id": "x03", "question": "คำถามทดสอบที่ไม่ซ้ำ 3", "intent": "problem", "module": "AP",
         "outcome": "ticket", "expected_sources": ["AP-1"], "must_include": []},
    ]
    path = tmp_path / "bad.jsonl"
    path.write_text("\n".join(json.dumps(b, ensure_ascii=False) for b in bad), encoding="utf-8")
    _, errors, _ = check(path)
    text = "\n".join(errors)
    assert "PO-99" in text                 # อ้างเอกสารที่ไม่มีอยู่จริง
    assert "อะไรสักอย่าง" in text          # คำที่ต้องมีในคำตอบ ไม่อยู่ในเอกสารที่อ้าง
    assert "UNKNOWN" in text               # คำถามนอกขอบเขตต้องไม่มีโมดูล
    assert "x03" in text                   # ticket ต้องไม่มี expected_sources
