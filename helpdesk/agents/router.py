"""Router agent — อ่านข้อความผู้ใช้แล้วตัดสินว่าเป็นคำถามวิธีใช้ แจ้งปัญหา หรือไม่เกี่ยว
พร้อมระบุโมดูล และเขียนคำค้นใหม่ให้ค้นในคู่มือได้ดีขึ้น"""
from .. import config
from ..llm import LLMError, chat_json
from ..modules import ERROR_CODE, MODULE_CODES, MODULES, guess_module

INTENTS = ["how_to", "problem", "out_of_scope"]

SYSTEM = f"""คุณคือ Router ของระบบ Helpdesk สำหรับโปรแกรม SiteERP (ERP สำหรับบริษัทรับเหมาก่อสร้าง)
จัดประเภทข้อความของผู้ใช้ แล้วตอบเป็น JSON เท่านั้น

ผู้ใช้ทุกคนเป็นพนักงานที่ใช้ SiteERP อยู่แล้ว ถ้าพูดถึง "ระบบ" "โปรแกรม" "แอป" หรือเอกสารในระบบโดยไม่เอ่ยชื่อ ให้ถือว่าหมายถึง SiteERP
ใช้ out_of_scope เฉพาะเรื่องที่ไม่ใช่การใช้งานซอฟต์แวร์นี้ เช่น สภาพอากาศ ร้านอาหาร งานเขียนทั่วไป หรือความรู้วิชาชีพ (สูตรคำนวณ วิธีก่อสร้าง กฎหมาย)

intent:
- how_to = ถามวิธีใช้งาน ขั้นตอน เงื่อนไข หรือความหมายของฟีเจอร์
- problem = แจ้งว่าใช้งานไม่ได้ มี error โปรแกรมค้าง หรือผลลัพธ์ผิดปกติ
- out_of_scope = ไม่เกี่ยวกับการใช้งาน SiteERP

module (เลือก 1):
{chr(10).join(f"- {code} = {info['name']}" for code, info in MODULES.items())}
- UNKNOWN = ระบุไม่ได้
ถ้ามีรหัส error เช่น PO-E02 ให้ใช้ส่วนหน้าของรหัสเป็น module

rewritten_query: เขียนข้อความของผู้ใช้ใหม่เป็นคำถามภาษาไทยที่ชัดเจน ใช้ศัพท์แบบในคู่มือ เพื่อนำไปค้นหา
(คงรหัส error และตัวเลขสำคัญไว้ทุกตัว)

ตัวอย่าง:
"ของมาไม่ครบ ทำไงดี" -> {{"intent": "how_to", "module": "RCV", "rewritten_query": "บันทึกรับสินค้าบางส่วนเมื่อของมาส่งไม่ครบทำอย่างไร"}}
"กดอนุมัติ PR แล้วขึ้น PR-E02" -> {{"intent": "problem", "module": "PR", "rewritten_query": "อนุมัติใบขอซื้อแล้วเกิดข้อผิดพลาดรหัส PR-E02"}}
"วันนี้ฝนตกไหม" -> {{"intent": "out_of_scope", "module": "UNKNOWN", "rewritten_query": "วันนี้ฝนตกไหม"}}"""

SCHEMA = {
    "type": "object",
    "properties": {
        "intent": {"type": "string", "enum": INTENTS},
        "module": {"type": "string", "enum": MODULE_CODES},
        "rewritten_query": {"type": "string"},
    },
    "required": ["intent", "module", "rewritten_query"],
}

PROBLEM_WORDS = ["ไม่ได้", "ไม่ผ่าน", "error", "ขึ้นว่า", "ค้าง", "เพี้ยน", "ผิดพลาด", "ถูกระงับ", "ใช้ไม่ได้"]
SCOPE_WORDS = ["ระบบ", "อนุมัติ", "เอกสาร", "รายงาน", "เมนู", "siteerp", "โปรแกรม", "บันทึก", "error"]


def route_by_rules(question: str) -> dict:
    """กฎแบบ keyword ใช้ใน stub mode และใช้สำรองเมื่อเรียก LLM ไม่สำเร็จ"""
    q = question.lower()
    module = guess_module(question)
    if module == "UNKNOWN" and not any(w in q for w in SCOPE_WORDS):
        intent = "out_of_scope"
    elif any(w in q for w in PROBLEM_WORDS) or ERROR_CODE.search(question):
        intent = "problem"
    else:
        intent = "how_to"
    return {"intent": intent, "module": module, "rewritten_query": question}


def route(question: str) -> tuple[dict, str]:
    """คืน (ผลการ route, วิธีที่ใช้)"""
    if config.BACKEND == "stub":
        return route_by_rules(question), "rules"
    try:
        out = chat_json(SYSTEM, question, SCHEMA)
        if out.get("intent") not in INTENTS or out.get("module") not in MODULE_CODES:
            raise LLMError(f"ค่าไม่อยู่ในตัวเลือก: {out}")
        rewritten = (out.get("rewritten_query") or question).strip()
        # กันโมเดลเขียนคำค้นใหม่แล้วทำรหัส error หาย เพราะรหัสคือสิ่งที่ค้นเจอได้แม่นที่สุด
        missing = [m.group(0).upper() for m in ERROR_CODE.finditer(question) if m.group(0).upper() not in rewritten.upper()]
        out["rewritten_query"] = " ".join([rewritten, *missing])
        return out, "llm"
    except LLMError as e:
        fallback = route_by_rules(question)
        fallback["error"] = str(e)
        return fallback, "rules (fallback)"
