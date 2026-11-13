"""Knowledge agent — ทำงาน 2 จังหวะ แยกเป็น 2 คำสั่งเล็ก ๆ เพื่อให้โมเดลขนาดเล็กทำได้นิ่ง:
  1) answer()         ตอบจากคู่มือ/FAQ ที่ค้นมาได้เท่านั้น โดยต้องยกประโยคหลักฐานมาด้วย แล้วโค้ดตรวจว่ามีจริง (grounded)
  2) propose_query()  ถ้าตอบไม่ได้ ให้ตัดสินใจเองว่าควรค้นอีกรอบไหม และเขียนคำค้นใหม่เอง
ถ้าตอบไม่ได้และไม่ค้นต่อ graph จะส่งให้ Ticket agent แทนการเดา"""
import re
from difflib import SequenceMatcher

from .. import config
from ..llm import LLMError, chat_json
from ..modules import ERROR_CODE

SYSTEM_RULES = """คุณคือเจ้าหน้าที่ Helpdesk ของโปรแกรม SiteERP ตอบคำถามโดยใช้ข้อมูลใน CONTEXT เท่านั้น ตอบเป็น JSON

กติกา:
1. อ่าน CONTEXT ให้ครบทุก doc ก่อนตัดสิน คำตอบอาจอยู่ใน doc ที่ไม่ใช่อันแรก หรืออยู่แค่ประโยคเดียว
2. ถ้ามี doc ใดระบุข้อเท็จจริงหรือขั้นตอนที่ตอบคำถามได้ ให้ grounded = true ตอบเป็นภาษาไทยสั้น กระชับ
   ถ้าเป็นขั้นตอนให้เรียงเป็นข้อ และใส่ id ของ doc ที่ใช้ (เช่น "PO-4") ใน citations
   ผู้ใช้มักใช้คำไม่ตรงกับคู่มือ (เช่น "ย้ายงบ" = "โอนงบ", "กี่เจ้า" = "กี่ราย") ให้ถือว่าเป็นเรื่องเดียวกัน
3. ข้อความแจ้งเตือนหรือเงื่อนไขที่คู่มืออธิบายไว้ (เช่น งบประมาณคงเหลือไม่พอ ผู้ขายถูกระงับ รับเกินจำนวนสั่งซื้อ)
   ถือว่าคู่มือมีวิธีแก้ ให้ grounded = true แล้วตอบวิธีแก้ตามคู่มือ
4. ถ้าไม่มี doc ใดตอบได้ ให้ grounded = false, answer = "" ห้ามเดาหรือแต่งขั้นตอนขึ้นเอง
5. ถ้าผู้ใช้แจ้งรหัส error ที่ไม่ปรากฏใน CONTEXT ให้ grounded = false
6. ถ้าผู้ใช้แจ้งว่าโปรแกรมทำงานผิดปกติ (เช่น ค้าง หน้าจอขาว ตัวอักษรเพี้ยน เข้าระบบไม่ได้ทั้งบริษัท)
   และ CONTEXT มีแค่วิธีใช้งานปกติ ไม่ได้พูดถึงอาการนั้น ให้ grounded = false"""

# ตัวอย่าง 2 แบบ (few-shot): ผลทดลองใน tools/experiment.py พบว่าช่วยให้โมเดลขนาด 7B ตัดสิน grounded ได้นิ่งขึ้นมาก
# ใช้โมดูลสมมติ (ใบลา) ที่ไม่มีในคู่มือจริง เพื่อไม่ให้เนื้อหาคู่มือหรือเฉลยของชุดทดสอบรั่วเข้า prompt
_EX_DOCS = ('<doc id="HR-2">\n[ใบลา (HR) > การยื่นใบลา]\nพนักงานยื่นใบลาได้ที่เมนู บุคคล > ใบลา > สร้างใหม่\n</doc>\n\n'
            '<doc id="HR-3">\n[ใบลา (HR) > สิทธิ์วันลา]\nลาพักร้อนได้ปีละ 10 วัน ลาป่วยเกิน 2 วันต้องแนบใบรับรองแพทย์\n</doc>')
FEWSHOT = f'''

ตัวอย่างที่ 1 (คำตอบอยู่ใน doc ที่สอง และผู้ใช้ใช้คำไม่ตรงคู่มือ)
CONTEXT:
{_EX_DOCS}
ข้อความจากผู้ใช้: หยุดพักผ่อนได้กี่วันต่อปี
ผลลัพธ์: {{"grounded": true, "answer": "ลาพักร้อนได้ปีละ 10 วัน", "citations": ["HR-3"]}}

ตัวอย่างที่ 2 (แจ้งอาการผิดปกติที่คู่มือไม่ได้พูดถึง)
CONTEXT:
{_EX_DOCS}
ข้อความจากผู้ใช้: กดส่งใบลาแล้วหน้าจอดับ
ผลลัพธ์: {{"grounded": false, "answer": "", "citations": []}}'''

SYSTEM = SYSTEM_RULES + FEWSHOT

SCHEMA = {
    "type": "object",
    "properties": {
        "grounded": {"type": "boolean"},
        "answer": {"type": "string"},
        "citations": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["grounded", "answer", "citations"],
}

# ---- วิธีที่ใช้จริง: ให้โมเดลคัดลอกประโยคหลักฐานก่อนตอบ แล้วโค้ดตรวจว่าประโยคนั้นมีในเอกสารจริง ----
SYSTEM_EVIDENCE = """คุณคือเจ้าหน้าที่ Helpdesk ของโปรแกรม SiteERP ตอบคำถามโดยใช้ข้อมูลใน CONTEXT เท่านั้น ตอบเป็น JSON ทำ 2 ขั้น

ขั้นที่ 1 หาหลักฐาน: อ่าน CONTEXT ให้ครบทุก doc แล้วคัดลอก "ประโยคที่ตอบคำถามได้ตรงที่สุด" มาใส่ evidence
แบบคำต่อคำ ห้ามแก้คำ และใส่ id ของ doc นั้นใน doc_id
- ผู้ใช้มักใช้คำไม่ตรงกับคู่มือ (เช่น "ย้ายงบ" = "โอนงบ", "กี่เจ้า" = "กี่ราย") ให้ถือว่าเป็นเรื่องเดียวกัน
- ข้อความแจ้งเตือนหรือเงื่อนไขที่คู่มืออธิบายไว้ ถือว่าคู่มือมีวิธีแก้ ให้คัดลอกประโยควิธีแก้มา
- ถ้าไม่มีประโยคใดตอบคำถามได้ ให้ evidence = "" และ doc_id = ""
- ถ้าผู้ใช้แจ้งรหัส error ที่ไม่ปรากฏใน CONTEXT หรือแจ้งว่าโปรแกรมทำงานผิดปกติ (เช่น ค้าง หน้าจอขาว ตัวอักษรเพี้ยน
  ช้า เข้าระบบไม่ได้ ตัวเลขในรายงานผิด) โดยที่ CONTEXT ไม่ได้พูดถึงอาการนั้น ให้ evidence = ""

ขั้นที่ 2 ตอบ: ถ้ามี evidence ให้เขียน answer เป็นภาษาไทยสั้น กระชับ โดยใช้ข้อมูลจาก doc นั้นเท่านั้น และใส่เงื่อนไขหรือตัวเลข
สำคัญที่อยู่ในประโยคหลักฐานให้ครบ ถ้าเป็นขั้นตอนให้เรียงเป็นข้อ ถ้าไม่มี evidence ให้ answer = "" ห้ามเดา"""
SCHEMA_EVIDENCE = {"type": "object",
            "properties": {"evidence": {"type": "string"}, "doc_id": {"type": "string"}, "answer": {"type": "string"}},
            "required": ["evidence", "doc_id", "answer"]}


def squash(s: str) -> str:
    return "".join(s.split()).lower()


def evidence_in_docs(evidence: str, hits: list[dict]) -> str | None:
    """โค้ดตรวจว่าประโยคหลักฐานมีอยู่จริงในเอกสาร คืน id ของเอกสารที่เจอ (ยอมให้ต่างได้เล็กน้อย)"""
    ev = squash(evidence)
    if len(ev) < 12:
        return None
    for h in hits:
        doc = squash(h["text"])
        if ev in doc:
            return h["id"]
        m = SequenceMatcher(None, ev, doc, autojunk=False).find_longest_match(0, len(ev), 0, len(doc))
        if m.size >= 0.7 * len(ev):
            return h["id"]
    return None


RETRY_SYSTEM = """คุณคือเจ้าหน้าที่ Helpdesk ของโปรแกรม SiteERP กำลังค้นคู่มือเพื่อตอบคำถามวิธีใช้งาน
เอกสารที่ค้นได้รอบก่อนยังตอบคำถามไม่ได้ ให้ตัดสินใจว่าควรค้นอีกรอบหรือไม่ ตอบเป็น JSON
- ถ้าคู่มือน่าจะมีคำตอบแต่คำค้นยังไม่ตรง ให้ retry = true และใส่ new_query เป็นคำค้นภาษาไทยสั้น ๆ
  ที่ใช้คำต่างจากคำค้นที่ลองแล้ว เช่น ชื่อเมนู ชื่อเอกสาร หรือคำพ้องความหมาย
- ถ้าดูจากหัวข้อเอกสารแล้วคู่มือไม่น่ามีเรื่องนี้ ให้ retry = false และ new_query = \"\""""

RETRY_SCHEMA = {
    "type": "object",
    "properties": {"retry": {"type": "boolean"}, "new_query": {"type": "string"}},
    "required": ["retry", "new_query"],
}


def format_context(hits: list[dict]) -> str:
    return "\n\n".join(f"<doc id=\"{h['id']}\">\n{h['text']}\n</doc>" for h in hits)


def _ngrams(s: str, n: int = 3) -> set[str]:
    s = re.sub(r"\s+", "", s.lower())
    return {s[i:i + n] for i in range(len(s) - n + 1)}


def answer_by_rules(question: str, intent: str, hits: list[dict]) -> dict:
    """ตอบแบบดึงประโยคที่ใกล้คำถามที่สุดจากเอกสารอันดับต้น ใช้ใน stub mode / fallback"""
    codes = {m.group(0).upper() for m in ERROR_CODE.finditer(question)}
    if codes:
        for h in hits:
            for line in h["text"].split("\n"):
                if any(c in line.upper() for c in codes):
                    return {"grounded": True, "answer": line, "citations": [h["id"]]}
        return {"grounded": False, "answer": "", "citations": []}

    top = hits[0]
    needed = config.MIN_SCORE + (0.15 if intent == "problem" else 0.0)  # แจ้งปัญหาต้องมั่นใจกว่า
    if top["score"] < needed:
        return {"grounded": False, "answer": "", "citations": []}
    q = _ngrams(question)
    lines = [l for l in top["text"].split("\n")[1:] if l.strip()]
    best = sorted(lines, key=lambda l: len(q & _ngrams(l)), reverse=True)[:2]
    ordered = [l for l in lines if l in best]
    return {"grounded": True, "answer": "\n".join(ordered), "citations": [top["id"]]}


def answer(question: str, intent: str, hits: list[dict]) -> tuple[dict, str]:
    # ด่านกันด้วยโค้ด: ผู้ใช้แจ้งรหัส error ที่ไม่มีในเอกสารที่ค้นได้ → ไม่ให้โมเดลมีโอกาสเดาวิธีแก้
    codes = {m.group(0).upper() for m in ERROR_CODE.finditer(question)}
    if codes and not any(c in h["text"].upper() for h in hits for c in codes):
        return {"grounded": False, "answer": "", "citations": []}, f"rule: ไม่พบ {', '.join(sorted(codes))} ในคู่มือ"
    if config.BACKEND == "stub":
        return answer_by_rules(question, intent, hits), "rules"
    user = f"CONTEXT:\n{format_context(hits)}\n\nประเภท: {intent}\nข้อความจากผู้ใช้: {question}"
    try:
        out = chat_json(SYSTEM_EVIDENCE, user, SCHEMA_EVIDENCE)
    except LLMError as e:
        return {"grounded": False, "answer": "", "citations": [], "error": str(e)}, "llm error → ส่งต่อ ticket"

    # โมเดลไม่ได้เป็นคนตัดสินว่า "มีหลักฐาน" — โค้ดตรวจเองว่าประโยคที่ยกมามีอยู่จริงในเอกสารที่ค้นได้
    evidence = (out.get("evidence") or "").strip()
    found_in = evidence_in_docs(evidence, hits)
    grounded = found_in is not None and bool(out.get("answer", "").strip())
    how = "llm + ตรวจหลักฐาน" if grounded or not evidence else "llm (หลักฐานที่ยกมาไม่พบในเอกสาร → ไม่ใช้คำตอบ)"
    return {"grounded": grounded, "answer": out.get("answer", "").strip() if grounded else "",
            "citations": [found_in] if grounded else [], "evidence": evidence if grounded else ""}, how


def propose_query(question: str, hits: list[dict], tried_queries: list[str]) -> str:
    """ให้ agent ตัดสินใจเองว่าจะค้นอีกรอบไหม คืนคำค้นใหม่ หรือ "" ถ้าไม่ค้นต่อ

    โค้ดเป็นคนตรวจผลอีกชั้น: คำค้นต้องไม่ว่างและไม่ซ้ำกับที่ลองแล้ว (กันวนค้นคำเดิม)"""
    if config.BACKEND == "stub":
        return ""
    titles = "\n".join(f"- {h['id']}: {h['title']}" for h in hits)
    user = f"คำถามของผู้ใช้: {question}\nคำค้นที่ลองแล้ว: {' | '.join(tried_queries)}\nหัวข้อเอกสารที่ค้นได้:\n{titles}"
    try:
        out = chat_json(RETRY_SYSTEM, user, RETRY_SCHEMA)
    except LLMError:
        return ""
    new_query = (out.get("new_query") or "").strip()
    if not out.get("retry") or not new_query or new_query in tried_queries:
        return ""
    return new_query
