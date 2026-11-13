"""ขั้นที่ 1: Data preparation — ทำความสะอาด → แบ่ง chunk → ทำ embedding → เก็บลง Chroma

รัน:  python prep.py              (ทำครบทุกขั้น)
      python prep.py --no-index   (ทำแค่ clean + chunk ไม่ต้องเปิด Ollama)
      python prep.py --save-html docs/prep.html   (บันทึกรายงานบนหน้าจอเป็น HTML)
"""
import argparse
import json
import re
from pathlib import Path
from collections import Counter

from rich.console import Console
from rich.table import Table
from rich.terminal_theme import MONOKAI

from helpdesk import config
from helpdesk.prep.chunk import chunk_manual
from helpdesk.prep.clean import clean_text
from helpdesk.prep.faq import load_faq

console = Console(record=True)  # record=True เพื่อบันทึกหน้าจอเป็น HTML ได้

FIX_LABELS = {
    "header_footer_removed": "ลบหัว/ท้ายกระดาษ",
    "lines_rejoined": "ต่อบรรทัดที่ถูกตัด",
    "sara_am_fixed": "แก้สระอำที่แตก (ํา → ำ)",
    "zero_width_removed": "ลบ zero-width space",
    "thai_digits_converted": "แปลงเลขไทยเป็นอารบิก",
    "multi_space_collapsed": "ยุบช่องว่างซ้ำ",
}


def visible(s: str, n: int = 160) -> str:
    """แสดงอักขระที่มองไม่เห็นให้เห็นในรายงาน"""
    s = s[:n].replace("​", "⟨ZWSP⟩").replace("ํา", "⟨ํา⟩")
    return s.replace("\n", "⏎ ")


def first_section(text: str) -> str:
    m = re.search(r"^[0-9๐-๙]+\.\s", text, re.M)
    return text[m.start():] if m else text


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-index", action="store_true", help="ไม่สร้าง embedding/index")
    parser.add_argument("--save-html", metavar="PATH", help="บันทึกรายงานบนหน้าจอเป็นไฟล์ HTML")
    args = parser.parse_args()
    try:
        prepare(args)
    finally:
        if args.save_html:
            Path(args.save_html).parent.mkdir(parents=True, exist_ok=True)
            console.save_html(args.save_html, theme=MONOKAI)  # พื้นมืดแบบหน้าจอเทอร์มินัล


def prepare(args) -> None:

    clean_dir = config.PROCESSED_DIR / "clean"
    clean_dir.mkdir(parents=True, exist_ok=True)

    totals: Counter = Counter()
    per_file, chunks, sample = [], [], None

    # 1) คู่มือ (ข้อความดึงจาก PDF)
    for path in sorted(config.RAW_DIR.glob("manual_*.txt")):
        module = path.stem.split("_", 1)[1].upper()
        raw = path.read_text(encoding="utf-8")
        cleaned, stats = clean_text(raw)
        (clean_dir / path.name).write_text(cleaned, encoding="utf-8")
        file_chunks = chunk_manual(cleaned, module, path.name)
        chunks += file_chunks
        totals.update(stats)
        per_file.append((path.name, stats, len(file_chunks)))
        if sample is None:
            sample = (path.name, raw, cleaned)

    # 2) FAQ จากระบบ Helpdesk เดิม
    faq_chunks, faq_stats, label_map = load_faq(config.RAW_DIR / "faq_export.csv")
    chunks += faq_chunks

    config.CHUNKS_FILE.write_text("\n".join(json.dumps(c, ensure_ascii=False) for c in chunks) + "\n", encoding="utf-8")

    # ---------- รายงาน ----------
    t = Table(title="Data preparation: คู่มือ (PDF → ข้อความ)")
    t.add_column("ไฟล์")
    for key in FIX_LABELS:
        t.add_column(FIX_LABELS[key], justify="right")
    t.add_column("chunks", justify="right")
    for name, stats, n in per_file:
        t.add_row(name, *[str(stats[k]) for k in FIX_LABELS], str(n))
    t.add_row("[bold]รวม", *[f"[bold]{totals[k]}" for k in FIX_LABELS], f"[bold]{sum(n for *_, n in per_file)}")
    console.print(t)

    f = Table(title="Data preparation: FAQ (CSV)")
    f.add_column("รายการ")
    f.add_column("จำนวน", justify="right")
    for key, label in [("faq_rows_in", "แถวที่รับเข้า"), ("faq_html_cleaned", "ล้าง HTML ในคำตอบ"),
                       ("faq_dropped_duplicate", "คำถามซ้ำ (เก็บฉบับล่าสุด)"),
                       ("faq_dropped_empty_answer", "คำตอบว่าง (ตัดทิ้ง)"), ("faq_chunks_out", "เหลือใช้งาน")]:
        f.add_row(label, str(faq_stats[key]))
    console.print(f)
    console.print("ปรับชื่อโมดูลให้เป็นมาตรฐาน: " + ", ".join(f"{k}→{v}" for k, v in label_map.items()))

    by_module = Counter(c["module"] for c in chunks)
    console.print("chunks ต่อโมดูล: " + ", ".join(f"{m}={n}" for m, n in sorted(by_module.items())))

    if sample:
        name, raw, cleaned = sample
        console.rule(f"ตัวอย่าง before / after ({name})")
        console.print("[red]BEFORE[/red] " + visible(first_section(raw), 260))
        console.print("[green]AFTER [/green] " + visible(first_section(cleaned), 260))

    report = {"manual": {k: totals[k] for k in ["chars_before", "chars_after", *FIX_LABELS]},
              "faq": dict(faq_stats), "faq_label_map": label_map,
              "chunks_total": len(chunks), "chunks_by_module": dict(by_module)}
    config.PREP_REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    # 3) Embedding + index
    if args.no_index:
        console.print(f"\nบันทึก {len(chunks)} chunks ที่ {config.CHUNKS_FILE.relative_to(config.ROOT)} (ข้ามการสร้าง index)")
        return
    from helpdesk.index import build_index
    from helpdesk.llm import LLMError
    try:
        with console.status(f"กำลังทำ embedding ด้วย {config.EMBED_MODEL if config.BACKEND == 'ollama' else 'hash (stub)'}..."):
            n = build_index(chunks)
    except LLMError as e:
        console.print(f"[red]สร้าง index ไม่สำเร็จ:[/red] {e}")
        raise SystemExit(1)
    console.print(f"\n[green]สร้าง index เสร็จ[/green] {n} chunks → {config.CHROMA_DIR.relative_to(config.ROOT)}")


if __name__ == "__main__":
    main()
