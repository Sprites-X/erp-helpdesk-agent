"""วัดว่าขั้นทำความสะอาดกู้ข้อความกลับมาได้ใกล้ต้นฉบับแค่ไหน

เพราะ data/raw สร้างจาก data/source เราจึงมี "เฉลย" ให้เทียบได้ ใช้ตอบคำถามว่า
"รู้ได้ยังไงว่า cleaning ทำงานถูก" ด้วยตัวเลข ไม่ใช่ความรู้สึก

รัน: python tools/check_clean_fidelity.py
"""
import difflib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from helpdesk.prep.clean import clean_text  # noqa: E402


def main():
    total = exact = loose = 0
    for src in sorted((ROOT / "data" / "source").glob("manual_*.md")):
        raw = ROOT / "data" / "raw" / f"{src.stem}.txt"
        cleaned, _ = clean_text(raw.read_text(encoding="utf-8"))
        a = [l for l in src.read_text(encoding="utf-8").split("\n") if l.strip()]
        b = [l for l in cleaned.split("\n") if l.strip()]
        e = sum(x == y for x, y in zip(a, b))
        s = sum(x.replace(" ", "") == y.replace(" ", "") for x, y in zip(a, b))
        total, exact, loose = total + len(a), exact + e, loose + s
        print(f"{src.stem:15s} ต้นฉบับ {len(a):3d} บรรทัด | หลัง clean {len(b):3d} | ตรงทุกตัวอักษร {e:3d} | ตรงถ้าไม่นับช่องว่าง {s:3d}")
        if len(a) != len(b) or s != len(a):
            for line in difflib.unified_diff(a, b, lineterm="", n=0):
                if not line.startswith(("---", "+++")):
                    print("    ", line[:110])
    print(f"\nรวม: ตรงทุกตัวอักษร {exact}/{total} ({exact / total:.0%}) | ตรงถ้าไม่นับช่องว่าง {loose}/{total} ({loose / total:.0%})")


if __name__ == "__main__":
    main()
