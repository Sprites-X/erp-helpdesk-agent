"""ทดสอบการแยกโมดูลและรหัส error"""
import pytest

from helpdesk.modules import ERROR_CODE, guess_module, normalize_module, team_for


@pytest.mark.parametrize("text, code", [
    ("แจ้งAP-E01", "AP-E01"),          # อักษรไทยติดกับรหัส: \b ใช้ไม่ได้เพราะอักษรไทยนับเป็น \w
    ("ขึ้น po-e03 ตอนอนุมัติ", "PO-E03"),
    ("BUDGET-E02)", "BUDGET-E02"),
])
def test_error_code_is_found(text, code):
    assert ERROR_CODE.search(text).group(0).upper() == code


@pytest.mark.parametrize("text", ["XAP-E01", "AP-E011", "AP-01", "HR-E01"])
def test_error_code_needs_exact_form(text):
    assert ERROR_CODE.search(text) is None


@pytest.mark.parametrize("label, code", [
    ("PO ", "PO"), ("po", "PO"), ("Purchase Order", "PO"), ("ใบขอซื้อ", "PR"),
    ("GR", "RCV"), ("บัญชีเจ้าหนี้", "AP"), ("Budget", "BUDGET"), ("", "GENERAL"),
])
def test_normalize_module(label, code):
    assert normalize_module(label) == code


def test_normalize_unknown_module():
    assert normalize_module("HR") is None


@pytest.mark.parametrize("text, module", [
    ("ขึ้น RCV-E02 ตอนบันทึกรับ PO", "RCV"),   # รหัส error ชนะ keyword
    ("โอนงบระหว่างรหัสต้นทุนยังไง", "BUDGET"),
    ("ตั้งหนี้แล้วหัก ณ ที่จ่ายผิด", "AP"),
    ("ลืมรหัสผ่าน", "GENERAL"),
    ("พรุ่งนี้ฝนตกไหม", "UNKNOWN"),
])
def test_guess_module(text, module):
    assert guess_module(text) == module


def test_short_english_keyword_must_be_whole_word():
    # 'pr' ต้องไม่ไปตรงกับ 'print'
    assert guess_module("print ใบเสร็จไม่ออก") != "PR"


def test_unknown_module_goes_to_it_helpdesk():
    assert team_for("UNKNOWN") == "IT Helpdesk L2"
