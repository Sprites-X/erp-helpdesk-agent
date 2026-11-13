"""ตรวจไฟล์ชุดคำถามทดสอบก่อนใช้ — โดยเฉพาะชุดที่คนอื่นหรือโมเดลอื่นเขียนมา

ตรวจ:
  - รูปแบบ JSON และ field ครบ ค่าอยู่ในตัวเลือกที่ระบบรู้จัก
  - เฉลยสอดคล้องกันเอง (เช่น outcome=answer ต้องมี expected_sources และ must_include)
  - id ของเอกสารใน expected_sources มีอยู่จริงในคลัง
  - คำใน must_include ปรากฏอยู่ในเอกสารที่อ้างจริง (ถ้าไม่ปรากฏ แปลว่าเฉลยอาจผิด หรือข้อเท็จจริงนั้นไม่ได้อยู่ในคู่มือ)
  - id และคำถามไม่ซ้ำกับชุดอื่นใน data/eval

รัน: python tools/check_eval_set.py data/eval/external_gemini.jsonl
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from helpdesk import config  # noqa: E402
from helpdesk.modules import MODULE_CODES  # noqa: E402
from helpdesk.prep.chunk import chunk_manual  # noqa: E402
from helpdesk.prep.clean import clean_text  # noqa: E402
from helpdesk.prep.faq import load_faq  # noqa: E402

FIELDS = ["id", "question", "intent", "module", "outcome", "expected_sources", "must_include"]
INTENTS = {"how_to", "problem", "out_of_scope"}
OUTCOMES = {"answer", "ticket", "out_of_scope"}


def knowledge_base() -> dict[str, str]:
    """สร้าง id → ข้อความของทุก chunk แบบเดียวกับ prep.py (ไม่ต้องทำ embedding)"""
    chunks = []
    for path in sorted(config.RAW_DIR.glob("manual_*.txt")):
        cleaned, _ = clean_text(path.read_text(encoding="utf-8"))
        chunks += chunk_manual(cleaned, path.stem.split("_", 1)[1].upper(), path.name)
    chunks += load_faq(config.RAW_DIR / "faq_export.csv")[0]
    kb = {}
    for c in chunks:
        kb.setdefault(c["id"].split("#")[0], "")
        kb[c["id"].split("#")[0]] += c["text"]
    return kb


def squash(s: str) -> str:
    return "".join(s.split()).lower()


def check(target: Path) -> tuple[list[dict], list[str], list[str]]:
    """ตรวจไฟล์ชุดคำถาม 1 ไฟล์ คืน (รายการคำถาม, ข้อผิดพลาด, คำเตือน)"""
    target = Path(target).resolve()
    kb = knowledge_base()

    seen_ids, seen_q = {}, {}
    for other in sorted((ROOT / "data" / "eval").glob("*.jsonl")):
        if other.resolve() == target:
            continue
        for line in other.read_text(encoding="utf-8-sig").splitlines():
            if line.strip():
                item = json.loads(line)
                seen_ids[item["id"]] = other.name
                seen_q[squash(item["question"])] = other.name

    errors, warnings, items = [], [], []
    for n, line in enumerate(target.read_text(encoding="utf-8-sig").splitlines(), 1):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError as e:
            errors.append(f"บรรทัด {n}: ไม่ใช่ JSON ({e.msg})")
            continue
        tag = f"บรรทัด {n} ({item.get('id', '?')})"
        missing = [f for f in FIELDS if f not in item]
        extra = [k for k in item if k not in FIELDS]
        if missing:
            errors.append(f"{tag}: ขาด field {missing}")
            continue
        if extra:
            warnings.append(f"{tag}: มี field เกิน {extra} (ไม่ถูกใช้)")
        items.append(item)

        if item["id"] in seen_ids:
            errors.append(f"{tag}: id ซ้ำกับใน {seen_ids[item['id']]}")
        seen_ids[item["id"]] = target.name
        if squash(item["question"]) in seen_q:
            errors.append(f"{tag}: คำถามซ้ำกับใน {seen_q[squash(item['question'])]}")
        seen_q[squash(item["question"])] = target.name

        if item["intent"] not in INTENTS:
            errors.append(f"{tag}: intent '{item['intent']}' ต้องเป็นหนึ่งใน {sorted(INTENTS)}")
        if item["module"] not in MODULE_CODES:
            errors.append(f"{tag}: module '{item['module']}' ต้องเป็นหนึ่งใน {MODULE_CODES}")
        if item["outcome"] not in OUTCOMES:
            errors.append(f"{tag}: outcome '{item['outcome']}' ต้องเป็นหนึ่งใน {sorted(OUTCOMES)}")

        oos = item["outcome"] == "out_of_scope"
        if oos != (item["intent"] == "out_of_scope"):
            errors.append(f"{tag}: outcome กับ intent ไม่สอดคล้องกัน (out_of_scope ต้องคู่กัน)")
        if oos and item["module"] != "UNKNOWN":
            errors.append(f"{tag}: คำถามนอกขอบเขตต้องมี module = UNKNOWN")
        if item["outcome"] == "answer":
            if not item["expected_sources"] or not item["must_include"]:
                errors.append(f"{tag}: outcome=answer ต้องมี expected_sources และ must_include")
            bad = [s for s in item["expected_sources"] if s not in kb]
            if bad:
                errors.append(f"{tag}: ไม่มีเอกสาร id {bad} ในคลัง")
            cited = squash("".join(kb.get(s, "") for s in item["expected_sources"]))
            for word in item["must_include"]:
                if squash(word) not in cited:
                    errors.append(f"{tag}: คำ '{word}' ไม่อยู่ในเอกสารที่อ้าง — เฉลยอาจผิด")
        elif item["expected_sources"] or item["must_include"]:
            errors.append(f"{tag}: outcome={item['outcome']} ต้องให้ expected_sources และ must_include เป็น []")

    return items, errors, warnings


def main():
    if len(sys.argv) != 2:
        print(__doc__)
        raise SystemExit(2)
    target = Path(sys.argv[1])
    items, errors, warnings = check(target)
    print(f"{target.name}: {len(items)} ข้อ — "
          + ", ".join(f"{o}={sum(i['outcome'] == o for i in items)}" for o in sorted(OUTCOMES)))
    for w in warnings:
        print("  [WARN]", w)
    for e in errors:
        print("  [FAIL]", e)
    if errors:
        print(f"\nเจอปัญหา {len(errors)} ข้อ แก้ไฟล์แล้วรันใหม่")
        raise SystemExit(1)
    print("ผ่าน: ใช้รัน eval ได้ แต่ยังต้องอ่านเฉลยทีละข้อด้วยตัวเองว่าตรงกับคู่มือจริง")


if __name__ == "__main__":
    main()
