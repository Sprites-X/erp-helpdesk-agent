"""Ticket agent — เมื่อตอบจากคู่มือไม่ได้ สรุปปัญหาเป็น Ticket ที่ทีม Support อ่านแล้วทำงานต่อได้ทันที

แบ่งหน้าที่ชัดเจน: LLM ทำส่วนที่ต้องใช้ภาษา (หัวข้อ สรุป ความเร่งด่วน ข้อมูลที่ต้องขอเพิ่ม)
ส่วนที่เป็นกฎตายตัว (เลข Ticket, ทีมที่รับผิดชอบ, เวลา) ให้โค้ดทำ เพราะต้องถูกต้อง 100%"""
import json
import secrets
from datetime import datetime

from .. import config
from ..llm import LLMError, chat_json
from ..modules import MODULES, team_for

PRIORITIES = ["urgent", "high", "medium", "low"]

SYSTEM = """คุณคือ Ticket Agent ของ Helpdesk โปรแกรม SiteERP สรุปปัญหาของผู้ใช้ให้ทีม Support อ่านแล้วเข้าใจทันที ตอบเป็น JSON
- title: หัวข้อสั้น ไม่เกิน 60 ตัวอักษร
- priority: urgent = หลายคนหรือทั้งบริษัทใช้งานไม่ได้ หรือกระทบการจ่ายเงิน
            high = ผู้ใช้ทำงานต่อไม่ได้
            medium = ยังมีทางเลี่ยง
            low = เป็นคำถามหรือข้อเสนอแนะ
- summary: สรุปปัญหา 1-2 ประโยค
- info_needed: ข้อมูลที่ทีม Support ควรขอเพิ่มจากผู้ใช้ 2-3 ข้อ (เช่น เลขที่เอกสาร ภาพหน้าจอ เวลาที่เกิด จำนวนผู้ใช้ที่เจอ)"""

SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "priority": {"type": "string", "enum": PRIORITIES},
        "summary": {"type": "string"},
        "info_needed": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["title", "priority", "summary", "info_needed"],
}


def draft_by_rules(question: str, module: str) -> dict:
    q = question.lower()
    if any(w in q for w in ["ทั้งออฟฟิศ", "ทั้งบริษัท", "ทุกคน", "จ่ายเงินไม่ได้"]):
        priority = "urgent"
    elif any(w in q for w in ["ไม่ได้", "ค้าง", "error", "ไม่ผ่าน"]):
        priority = "high"
    else:
        priority = "medium"
    return {
        "title": question[:60],
        "priority": priority,
        "summary": question,
        "info_needed": ["เลขที่เอกสารที่เกี่ยวข้อง", "ภาพหน้าจอตอนเกิดปัญหา", "เวลาที่เกิดปัญหา"],
    }


def create_ticket(question: str, intent: str, module: str, hits: list[dict], save: bool = True) -> tuple[dict, str]:
    checked = [f"{h['id']} {h['title']}" for h in hits[:3]]
    if config.BACKEND == "stub":
        draft, how = draft_by_rules(question, module), "rules"
    else:
        user = (f"ข้อความจากผู้ใช้: {question}\nประเภท: {intent}\nโมดูล: {module}\n"
                f"เอกสารที่ระบบค้นแล้วแต่ไม่พบวิธีแก้: {', '.join(checked) or '-'}")
        try:
            draft, how = chat_json(SYSTEM, user, SCHEMA), "llm"
            if draft.get("priority") not in PRIORITIES:
                draft["priority"] = "medium"
        except LLMError:
            draft, how = draft_by_rules(question, module), "rules (fallback)"

    now = datetime.now()
    ticket = {
        "ticket_id": f"T-{now:%y%m%d-%H%M%S}-{secrets.token_hex(2).upper()}",
        "created_at": now.isoformat(timespec="seconds"),
        "status": "open",
        "module": module,
        "module_name": MODULES.get(module, {}).get("name", "ไม่ทราบ"),
        "assigned_team": team_for(module),
        **draft,
        "original_message": question,
        "kb_checked": checked,
    }
    if save:
        config.TICKET_DIR.mkdir(parents=True, exist_ok=True)
        (config.TICKET_DIR / f"{ticket['ticket_id']}.json").write_text(
            json.dumps(ticket, ensure_ascii=False, indent=2), encoding="utf-8")
    return ticket, how
