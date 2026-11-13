"""ทดสอบการเตรียม FAQ ที่ export มาจากระบบ Helpdesk เดิม (ข้อมูลไม่สะอาดโดยตั้งใจ)"""
from helpdesk import config
from helpdesk.modules import MODULES
from helpdesk.prep.faq import html_to_text, load_faq


def test_faq_rows_are_cleaned():
    chunks, stats, label_map = load_faq(config.RAW_DIR / "faq_export.csv")
    ids = [c["id"] for c in chunks]
    assert stats["faq_rows_in"] == 15
    assert len(chunks) == stats["faq_chunks_out"] == 13
    assert "FAQ-4" not in ids    # คำถามซ้ำกับ FAQ-5 แต่เก่ากว่า → เก็บอันใหม่
    assert "FAQ-14" not in ids   # ไม่มีคำตอบ
    assert len(set(ids)) == len(ids)
    assert all(c["module"] in MODULES for c in chunks)
    assert not any("<" in c["text"] or "&nbsp;" in c["text"] for c in chunks)
    assert label_map["'PO '"] == "PO"


def test_html_to_text():
    # ตัด tag ทิ้ง, <br> เป็นขึ้นบรรทัดใหม่, แปลง entity เช่น &amp; กลับเป็นตัวอักษร
    assert html_to_text("กด <b>บันทึก</b><br>R&amp;D ") == "กด บันทึก\nR&D"
