"""สร้างไฟล์ data/raw/manual_*.txt จาก data/source/*.md

ข้อมูลทั้งหมดเป็นข้อมูลจำลอง ไฟล์ใน data/source คือคู่มือฉบับสะอาด สคริปต์นี้ใส่ noise
แบบที่เจอจริงตอนดึงข้อความภาษาไทยออกจาก PDF เพื่อให้ขั้น data preparation มีของจริงให้แก้:
  - หัว/ท้ายกระดาษแทรกกลางเนื้อหาทุกหน้า
  - สระอำแตกเป็นนิคหิต + สระอา (U+0E4D U+0E32) แทนที่จะเป็น U+0E33
  - zero-width space แทรกในข้อความ
  - เลขไทยปนเลขอารบิก
  - ตัดบรรทัดกลางประโยคหรือกลางคำตามความกว้างหน้ากระดาษ
  - ช่องว่างซ้ำและช่องว่างท้ายบรรทัด

รัน: python tools/make_mock_raw.py   (ใช้ seed คงที่ ได้ผลเหมือนเดิมทุกครั้ง)
"""
import random
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "data" / "source"
OUT_DIR = ROOT / "data" / "raw"

WIDTH = 64            # ความกว้างบรรทัดในหน้ากระดาษจำลอง
LINES_PER_PAGE = 16   # จำนวนบรรทัดต่อหน้า ก่อนแทรกหัว/ท้ายกระดาษ
TH_DIGITS = "๐๑๒๓๔๕๖๗๘๙"
ZWSP = "​"
NIKHAHIT_AA = "ํา"
# บรรทัดต่อเนื่องห้ามขึ้นต้นเหมือนหัวข้อ/รายการ ไม่งั้นตอนประกอบกลับจะแยกไม่ออก
LOOKS_LIKE_ITEM = re.compile(r"^(\d|[-•]|รหัส|SiteERP)")


def is_thai(ch: str) -> bool:
    return "฀" <= ch <= "๿"


def add_noise(line: str, rng: random.Random) -> str:
    if rng.random() < 0.3:
        line = "".join(TH_DIGITS[int(c)] if c in "0123456789" else c for c in line)
    line = "".join(NIKHAHIT_AA if c == "ำ" and rng.random() < 0.5 else c for c in line)
    out = []
    for c in line:
        out.append(c)
        if is_thai(c) and rng.random() < 0.012:
            out.append(ZWSP)
    line = "".join(out)
    if rng.random() < 0.25:
        line = line.replace(" ", "  ", 1)
    return line


def wrap(line: str) -> list[str]:
    """ตัดบรรทัดยาวแบบ PDF โดยตัดได้เฉพาะระหว่างอักษรไทยหรือตรงช่องว่าง (ไม่ตัดกลางรหัสอย่าง PR-E01)"""
    pieces = []
    while len(line) > WIDTH:
        cut = None
        for p in range(WIDTH, WIDTH - 12, -1):
            left, right = line[p - 1], line[p]
            ok = left == " " or right == " " or (is_thai(left) and is_thai(right))
            if ok and not LOOKS_LIKE_ITEM.match(line[p:].lstrip()):
                cut = p
                break
        if cut is None:
            break
        pieces.append(line[:cut].rstrip())
        line = line[cut:].lstrip()
    pieces.append(line)
    return pieces


def make_raw(src: Path, rng: random.Random) -> str:
    lines = src.read_text(encoding="utf-8").splitlines()
    out, page, count = [], 1, 0
    for i, line in enumerate(lines):
        noisy = line if i == 0 else add_noise(line, rng)
        for piece in wrap(noisy) if noisy else [""]:
            if rng.random() < 0.3:
                piece += " " * rng.randint(1, 3)
            out.append(piece)
            count += 1
            if count >= LINES_PER_PAGE:
                page += 1
                out += ["", "เอกสารภายใน — ห้ามเผยแพร่", f"SiteERP คู่มือการใช้งาน v3.2 | หน้า {page}", ""]
                count = 0
    return "\n".join(out) + "\n"


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rng = random.Random(42)
    for src in sorted(SRC_DIR.glob("manual_*.md")):
        dst = OUT_DIR / f"{src.stem}.txt"
        dst.write_text(make_raw(src, rng), encoding="utf-8")
        print(f"wrote {dst.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
