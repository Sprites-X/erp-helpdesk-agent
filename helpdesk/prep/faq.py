"""เตรียม FAQ ที่ export มาจากระบบ Helpdesk เดิม (CSV)

ปัญหาที่แก้:
  - ชื่อโมดูลเขียนไม่เหมือนกัน (PR, pr, ใบขอซื้อ, 'PO ') → รหัสมาตรฐาน
  - คำตอบมี HTML (<b>, <br>, &gt;)
  - คำถามซ้ำ → เก็บฉบับที่อัปเดตล่าสุด
  - คำตอบว่าง → ตัดทิ้ง
"""
import csv
import html
import re
from collections import Counter
from pathlib import Path

from ..modules import MODULES, normalize_module


def html_to_text(s: str) -> str:
    s = re.sub(r"<br\s*/?>", "\n", s or "", flags=re.I)
    s = re.sub(r"<[^>]+>", "", s)
    return html.unescape(s).strip()


def load_faq(path: Path) -> tuple[list[dict], Counter, dict]:
    stats: Counter = Counter()
    label_map: dict[str, str] = {}
    latest: dict[str, dict] = {}

    with path.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            stats["faq_rows_in"] += 1
            raw_label = row.get("module", "")
            module = normalize_module(raw_label)
            if module is None:
                module = "GENERAL"
                stats["faq_unknown_module"] += 1
            if raw_label != module:
                label_map[repr(raw_label)] = module

            question = re.sub(r"\s+", " ", row.get("question", "")).strip()
            answer = html_to_text(row.get("answer", ""))
            if answer != (row.get("answer") or "").strip():
                stats["faq_html_cleaned"] += 1
            if not answer:
                stats["faq_dropped_empty_answer"] += 1
                continue

            key = re.sub(r"\s+", "", question.lower())
            item = {"id": row["id"], "module": module, "question": question,
                    "answer": answer, "updated_at": row.get("updated_at", "")}
            if key in latest:
                stats["faq_dropped_duplicate"] += 1
                if item["updated_at"] < latest[key]["updated_at"]:
                    continue
            latest[key] = item

    chunks = []
    for item in latest.values():
        m = item["module"]
        chunks.append({
            "id": f"FAQ-{item['id']}",
            "module": m,
            "title": item["question"],
            "source": path.name,
            "doc_type": "faq",
            "text": f"[FAQ {MODULES[m]['name']} ({m})]\nถาม: {item['question']}\nตอบ: {item['answer']}",
        })
    stats["faq_chunks_out"] = len(chunks)
    return chunks, stats, label_map
