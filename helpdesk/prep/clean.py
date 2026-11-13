"""ทำความสะอาดข้อความภาษาไทยที่ดึงมาจาก PDF

ปัญหาที่แก้ (นับจำนวนไว้ทุกข้อเพื่อทำรายงาน before/after):
  1. zero-width characters ที่มองไม่เห็นแต่ทำให้ค้นคำไม่เจอ
  2. สระอำแตกเป็น นิคหิต + สระอา (ํ + า) — ห้ามใช้ NFKC แก้ เพราะ NFKC แปลงไปทางตรงข้าม (ำ → ํา)
  3. เลขไทยปนเลขอารบิก
  4. หัว/ท้ายกระดาษที่แทรกกลางเนื้อหา
  5. บรรทัดที่ถูกตัดกลางประโยค — ประกอบกลับ โดยไม่เติมช่องว่างถ้ารอยต่อเป็นอักษรไทยทั้งสองฝั่ง
  6. ช่องว่างซ้ำ
"""
import re
from collections import Counter

ZERO_WIDTH = re.compile("[​‌‍⁠﻿]")
NIKHAHIT_AA = "ํา"
SARA_AM = "ำ"
THAI_DIGITS = "๐๑๒๓๔๕๖๗๘๙"
TH2AR = str.maketrans(THAI_DIGITS, "0123456789")
HEADER = re.compile(r"^\s*SiteERP\s+คู่มือการใช้งาน\s+v[\d.]+\s*\|\s*หน้า\s*\d+\s*$")
FOOTER = re.compile(r"^\s*เอกสารภายใน\s*[—–-]\s*ห้ามเผยแพร่\s*$")
# บรรทัดที่ขึ้นต้นแบบนี้คือจุดเริ่มเนื้อหาใหม่ ห้ามต่อเข้ากับบรรทัดก่อนหน้า
ITEM_START = re.compile(r"^(\d+\.\s|\d+\)\s|[-•]\s|รหัส\s|SiteERP\s)")
# หัวข้อ/ชื่อเอกสารสั้นพอที่จะไม่ถูกตัดบรรทัด จึงห้ามเอาบรรทัดถัดไปมาต่อท้าย
NO_APPEND = re.compile(r"^(\d+\.\s|SiteERP\s)")


def is_thai(ch: str) -> bool:
    return "฀" <= ch <= "๿"


def _drop_headers_footers(lines: list[str], stats: Counter) -> list[str]:
    is_hf = [bool(HEADER.match(l) or FOOTER.match(l)) for l in lines]
    kept = []
    for i, line in enumerate(lines):
        if is_hf[i]:
            stats["header_footer_removed"] += 1
            continue
        if not line.strip():
            # บรรทัดว่างที่อยู่ติดหัว/ท้ายกระดาษเป็นแค่รอยต่อหน้า ไม่ใช่การขึ้นย่อหน้าใหม่
            j = i - 1
            while j >= 0 and not lines[j].strip():
                j -= 1
            k = i + 1
            while k < len(lines) and not lines[k].strip():
                k += 1
            if (j >= 0 and is_hf[j]) or (k < len(lines) and is_hf[k]):
                continue
        kept.append(line)
    return kept


def _rejoin(lines: list[str], stats: Counter) -> list[str]:
    """ประกอบบรรทัดที่ถูกตัดกลับเป็นย่อหน้า

    บรรทัดที่ถูกตัดเพราะชนขอบกระดาษจะยาวเกือบเต็มบรรทัด ส่วนบรรทัดสุดท้ายของย่อหน้ามักสั้นกว่า
    จึงต่อบรรทัดถัดไปเข้ามาเฉพาะเมื่อบรรทัดก่อนหน้า "ยาวเกือบเต็ม" (>= 75% ของความยาวบรรทัดเต็มของเอกสาร)
    """
    lengths = sorted(len(l.strip()) for l in lines if l.strip())
    full_width = lengths[int(len(lengths) * 0.9)] if lengths else 0
    threshold = 0.75 * full_width

    out: list[str] = []
    prev_len = 0  # ความยาวของบรรทัดจริงบรรทัดล่าสุด (ก่อนต่อ)
    for line in lines:
        s = line.strip()
        collapsed = re.sub(r"[ \t]{2,}", " ", s)
        if collapsed != s:
            stats["multi_space_collapsed"] += 1
        if not collapsed:
            out.append("")
            prev_len = 0
            continue
        wrapped = prev_len >= threshold
        if out and out[-1] and wrapped and not ITEM_START.match(collapsed) and not NO_APPEND.match(out[-1]):
            prev = out[-1]
            sep = "" if is_thai(prev[-1]) and is_thai(collapsed[0]) else " "
            out[-1] = prev + sep + collapsed
            stats["lines_rejoined"] += 1
        else:
            out.append(collapsed)
        prev_len = len(s)
    return out


def clean_text(raw: str) -> tuple[str, Counter]:
    stats: Counter = Counter()
    stats["chars_before"] = len(raw)
    text = raw.replace("\r\n", "\n")

    stats["zero_width_removed"] = len(ZERO_WIDTH.findall(text))
    text = ZERO_WIDTH.sub("", text)

    stats["sara_am_fixed"] = text.count(NIKHAHIT_AA)
    text = text.replace(NIKHAHIT_AA, SARA_AM)

    stats["thai_digits_converted"] = sum(text.count(d) for d in THAI_DIGITS)
    text = text.translate(TH2AR)

    lines = _drop_headers_footers([l.rstrip() for l in text.split("\n")], stats)
    lines = _rejoin(lines, stats)

    text = re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip() + "\n"
    stats["chars_after"] = len(text)
    return text, stats
