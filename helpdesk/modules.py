"""นิยามโมดูลของ ERP จำลอง ใช้ร่วมกันทั้งขั้นเตรียมข้อมูล Router และ Ticket agent"""
import re

MODULES = {
    "PR": {
        "name": "ใบขอซื้อ",
        "aliases": ["pr", "ใบขอซื้อ", "purchase requisition"],
        "keywords": ["pr", "ใบขอซื้อ", "ขอซื้อ"],
        "team": "ทีม Support งานจัดซื้อ",
    },
    "PO": {
        "name": "ใบสั่งซื้อ",
        "aliases": ["po", "ใบสั่งซื้อ", "purchase order"],
        "keywords": ["po", "ใบสั่งซื้อ", "ผู้ขาย", "ใบเสนอราคา", "เปรียบเทียบราคา", "ราคากลาง"],
        "team": "ทีม Support งานจัดซื้อ",
    },
    "RCV": {
        "name": "รับสินค้า",
        "aliases": ["rcv", "gr", "รับของ", "รับสินค้า", "goods receipt"],
        "keywords": ["rcv", "gr", "รับของ", "รับสินค้า", "บันทึกรับ", "ของมา", "ชำรุด", "คืนสินค้า", "ซิงก์"],
        "team": "ทีม Support งานจัดซื้อ",
    },
    "AP": {
        "name": "เจ้าหนี้และการจ่ายเงิน",
        "aliases": ["ap", "เจ้าหนี้", "บัญชีเจ้าหนี้", "accounts payable"],
        "keywords": ["ap", "ตั้งหนี้", "เจ้าหนี้", "ใบแจ้งหนี้", "จ่ายเงิน", "เช็ค", "หัก ณ ที่จ่าย",
                     "ประกันผลงาน", "retention", "matching"],
        "team": "ทีม Support งานบัญชีการเงิน",
    },
    "BUDGET": {
        "name": "งบประมาณโครงการ",
        "aliases": ["budget", "งบ", "งบประมาณ"],
        "keywords": ["budget", "งบ", "boq", "รหัสต้นทุน"],
        "team": "ทีม Support งานควบคุมต้นทุน",
    },
    "GENERAL": {
        "name": "ทั่วไป",
        "aliases": ["general", "ทั่วไป", ""],
        "keywords": ["รหัสผ่าน", "เข้าระบบ", "ล็อกอิน", "login", "มือถือ", "แอป"],
        "team": "IT Helpdesk L2",
    },
}
MODULE_CODES = list(MODULES) + ["UNKNOWN"]
# ใช้ lookaround แทน \b เพราะอักษรไทยนับเป็น \w ทำให้ "แจ้งAP-E01" ไม่มี word boundary
ERROR_CODE = re.compile(r"(?<![A-Za-z0-9])(PR|PO|RCV|AP|BUDGET)-E\d{2}(?![0-9])", re.IGNORECASE)


def normalize_module(label: str) -> str | None:
    """แปลงชื่อโมดูลที่เขียนไม่เหมือนกัน (PR, pr, ใบขอซื้อ, 'PO ') ให้เป็นรหัสมาตรฐาน คืน None ถ้าไม่รู้จัก"""
    key = (label or "").strip().lower()
    for code, info in MODULES.items():
        if key in info["aliases"]:
            return code
    return None


def team_for(module: str) -> str:
    return MODULES.get(module, MODULES["GENERAL"])["team"]


def _keyword_hit(keyword: str, text: str) -> int:
    """คืนตำแหน่งที่เจอ keyword (-1 ถ้าไม่เจอ) คำภาษาอังกฤษต้องเป็นคำเต็ม กันไม่ให้ 'pr' ไปตรงกับ 'print'"""
    if keyword.isascii():
        m = re.search(rf"(?<![a-z]){re.escape(keyword)}(?![a-z])", text)
        return m.start() if m else -1
    return text.find(keyword)


def guess_module(text: str) -> str:
    """เดาโมดูลจาก keyword ใช้ใน stub mode และเป็น fallback เมื่อ LLM ใช้งานไม่ได้"""
    t = text.lower()
    code = ERROR_CODE.search(text)
    if code:
        return code.group(1).upper()
    best, best_key = "UNKNOWN", (0, 0)
    for module, info in MODULES.items():
        positions = [p for p in (_keyword_hit(k, t) for k in info["keywords"]) if p >= 0]
        if positions:
            key = (len(positions), -min(positions))  # เจอหลายคำก่อน ถ้าเท่ากันเอาคำที่โผล่ก่อน
            if key > best_key:
                best, best_key = module, key
    return best
