"""ทดสอบการตรวจว่าประโยคหลักฐานที่โมเดลยกมามีอยู่จริงในเอกสาร"""
from conftest import doc

from helpdesk.agents.knowledge import evidence_in_docs

TEXT = ("[งบประมาณโครงการ (BUDGET) > การโอนงบ]\n"
        "การโอนงบระหว่างรหัสต้นทุนต้องได้รับอนุมัติจากผู้จัดการโครงการ และโอนได้ไม่เกิน 10% ของงบรหัสต้นทาง")
HITS = [doc("BUDGET-1", "[งบประมาณโครงการ (BUDGET) > ภาพรวม]\nงบประมาณแยกตามรหัสต้นทุน", 0.7),
        doc("BUDGET-3", TEXT, 0.6)]


def test_exact_quote_is_found_in_the_right_doc():
    assert evidence_in_docs("โอนได้ไม่เกิน 10% ของงบรหัสต้นทาง", HITS) == "BUDGET-3"


def test_spacing_differences_are_ignored():
    assert evidence_in_docs("โอนได้ ไม่เกิน 10%ของงบ รหัสต้นทาง", HITS) == "BUDGET-3"


def test_small_edits_are_tolerated():
    # โมเดลมักคัดลอกมาเกือบตรง เช่นตัดคำท้าย ยอมให้ต่างได้ถ้าส่วนที่ตรงกันยาวอย่างน้อย 70%
    assert evidence_in_docs("ต้องได้รับอนุมัติจากผู้จัดการโครงการ และโอนได้ไม่เกิน 10% นะครับ", HITS) == "BUDGET-3"


def test_too_short_quote_is_rejected():
    assert evidence_in_docs("10%", HITS) is None


def test_invented_sentence_is_rejected():
    assert evidence_in_docs("ฝ่ายบัญชีโอนงบได้เองไม่จำกัดจำนวนโดยไม่ต้องขออนุมัติ", HITS) is None


def test_empty_quote_is_rejected():
    assert evidence_in_docs("", HITS) is None


def test_chunk_header_is_not_evidence():
    # หัวเรื่องที่เติมไว้หน้า chunk อยู่ในเอกสารจริง แต่บอกแค่ว่าเอกสารพูดเรื่องอะไร ไม่ได้ตอบคำถาม
    assert evidence_in_docs("[งบประมาณโครงการ (BUDGET) > การโอนงบ]", HITS) is None


def test_faq_question_line_is_not_evidence():
    faq = [doc("FAQ-3", "[FAQ ใบขอซื้อ (PR)]\nถาม: แนบไฟล์ใน PR ได้ขนาดเท่าไหร่\nตอบ: ไฟล์ละไม่เกิน 10 MB รวมไม่เกิน 5 ไฟล์", 0.8)]
    assert evidence_in_docs("ถาม: แนบไฟล์ใน PR ได้ขนาดเท่าไหร่", faq) is None
    assert evidence_in_docs("ตอบ: ไฟล์ละไม่เกิน 10 MB รวมไม่เกิน 5 ไฟล์", faq) == "FAQ-3"


def test_header_rule_can_be_switched_off_for_experiments(monkeypatch):
    from helpdesk import config
    monkeypatch.setattr(config, "STRICT_EVIDENCE", False)
    # แบบเดิมยอมรับหัวเรื่อง และยังจับคู่แบบคลาดเคลื่อนกับหัวเรื่องของเอกสารอื่นในโมดูลเดียวกันได้ด้วย
    assert evidence_in_docs("[งบประมาณโครงการ (BUDGET) > การโอนงบ]", HITS) is not None
