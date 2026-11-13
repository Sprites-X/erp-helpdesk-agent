"""แบ่งคู่มือที่ทำความสะอาดแล้วเป็น chunk ตามหัวข้อ พร้อม metadata

ทำไมแบ่งตามหัวข้อ ไม่ใช่ตัดทุก N ตัวอักษร: หัวข้อหนึ่งในคู่มือคือเรื่องเดียวกัน ถ้าตัดกลางหัวข้อ
ขั้นตอนที่ 3 อาจไปอยู่คนละ chunk กับขั้นตอนที่ 1 ส่วนหัวข้อที่ยาวเกินจะถูกตัดตามบรรทัดและซ้อนกัน 1 บรรทัด

แต่ละ chunk เติม "หัวเรื่อง" ไว้ข้างหน้า เช่น [ใบสั่งซื้อ (PO) > การแก้ไขใบสั่งซื้อหลังอนุมัติ]
เพื่อให้ embedding รู้บริบทแม้เนื้อหาใน chunk จะไม่ได้เอ่ยชื่อโมดูลเลย
"""
import re

from ..config import MAX_CHUNK_CHARS
from ..modules import MODULES

HEADING = re.compile(r"^(\d+)\.\s+(.+)$")


def split_long(lines: list[str], max_chars: int = MAX_CHUNK_CHARS) -> list[list[str]]:
    parts, cur, size = [], [], 0
    for line in lines:
        if cur and size + len(line) > max_chars:
            parts.append(cur)
            cur, size = [cur[-1]], len(cur[-1])  # overlap 1 บรรทัด
        cur.append(line)
        size += len(line)
    if cur:
        parts.append(cur)
    return parts


def chunk_manual(text: str, module: str, source: str) -> list[dict]:
    sections, current = [], None
    for line in text.split("\n"):
        m = HEADING.match(line)
        if m:
            current = {"num": m.group(1), "title": m.group(2).strip(), "lines": []}
            sections.append(current)
        elif current is not None and line.strip():
            current["lines"].append(line.strip())

    chunks = []
    for sec in sections:
        parts = split_long(sec["lines"])
        for i, part in enumerate(parts, 1):
            cid = f"{module}-{sec['num']}" + (f"#{i}" if len(parts) > 1 else "")
            header = f"[{MODULES[module]['name']} ({module}) > {sec['title']}]"
            chunks.append({
                "id": cid,
                "module": module,
                "title": sec["title"],
                "source": source,
                "doc_type": "manual",
                "text": header + "\n" + "\n".join(part),
            })
    return chunks
