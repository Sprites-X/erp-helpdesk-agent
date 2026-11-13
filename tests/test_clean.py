"""ทดสอบการทำความสะอาดข้อความภาษาไทยที่ดึงมาจาก PDF"""
from conftest import ROOT

from helpdesk.prep.clean import clean_text


def test_sara_am_is_rebuilt():
    # PDF บางตัวเก็บสระอำเป็น นิคหิต + สระอา ตาเห็นเหมือนกัน แต่ค้นคำว่า "ทำ" ไม่เจอ
    text, stats = clean_text("ทํางาน\n")
    assert text == "ทำงาน\n"
    assert stats["sara_am_fixed"] == 1


def test_zero_width_characters_are_removed():
    text, stats = clean_text("ใบ​สั่ง‍ซื้อ\n")
    assert text == "ใบสั่งซื้อ\n"
    assert stats["zero_width_removed"] == 2


def test_thai_digits_become_arabic():
    text, _ = clean_text("วงเงิน ๕๐,๐๐๐ บาท\n")
    assert text == "วงเงิน 50,000 บาท\n"


def test_header_and_footer_are_dropped():
    raw = ("เนื้อหาบรรทัดแรก\n\nSiteERP คู่มือการใช้งาน v2.1 | หน้า 3\n"
           "เอกสารภายใน — ห้ามเผยแพร่\n\nเนื้อหาบรรทัดสอง\n")
    text, stats = clean_text(raw)
    assert "SiteERP" not in text and "ห้ามเผยแพร่" not in text
    assert stats["header_footer_removed"] == 2


def test_wrapped_thai_lines_join_without_space():
    # ภาษาไทยไม่เว้นวรรคระหว่างคำ ถ้าต่อบรรทัดแล้วเติมช่องว่างจะได้คำที่ขาดกลาง เช่น "อนุมัติแ ล้ว"
    text, stats = clean_text("ก" * 40 + "\n" + "ข" * 10 + "\n")
    assert text == "ก" * 40 + "ข" * 10 + "\n"
    assert stats["lines_rejoined"] == 1


def test_wrapped_latin_lines_join_with_space():
    text, _ = clean_text("a" * 40 + "\n" + "b" * 10 + "\n")
    assert text == "a" * 40 + " " + "b" * 10 + "\n"


def test_numbered_steps_are_not_joined():
    text, _ = clean_text("ก" * 40 + "\n1. ขั้นตอนถัดไป\n")
    assert text.splitlines() == ["ก" * 40, "1. ขั้นตอนถัดไป"]


def test_short_line_is_end_of_paragraph():
    text, _ = clean_text("ก" * 40 + "\nสั้น\nบรรทัดใหม่\n")
    assert text.splitlines() == ["ก" * 40 + "สั้น", "บรรทัดใหม่"]


def test_cleaning_recovers_the_source_manuals():
    """data/raw สร้างจาก data/source จึงเทียบกับต้นฉบับได้ (ตัวเลขเดียวกับ tools/check_clean_fidelity.py)"""
    total = loose = 0
    for src in sorted((ROOT / "data" / "source").glob("manual_*.md")):
        cleaned, _ = clean_text((ROOT / "data" / "raw" / f"{src.stem}.txt").read_text(encoding="utf-8"))
        a = [l for l in src.read_text(encoding="utf-8").split("\n") if l.strip()]
        b = [l for l in cleaned.split("\n") if l.strip()]
        total += len(a)
        loose += sum(x.replace(" ", "") == y.replace(" ", "") for x, y in zip(a, b))
    assert total > 0
    assert loose / total >= 0.90
