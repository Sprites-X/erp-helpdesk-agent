"""เทียบผล eval หลายรอบ เช่น โมเดล 7B กับ 3B บนชุดคำถามเดียวกัน

รัน: python tools/compare_reports.py 7b 3b
     (อ่าน outputs/eval_report*_7b.json และ outputs/eval_report*_3b.json ทั้ง 3 ชุด)
"""
import json
import statistics
import sys
from pathlib import Path

from rich.console import Console
from rich.table import Table

ROOT = Path(__file__).resolve().parents[1]
SETS = [("eval_report", "ชุด 1"), ("eval_report_heldout", "ชุด 2"), ("eval_report_final_check", "ชุด 3")]
STAGES = ["Router", "Retriever", "Knowledge", "Ticket"]


def load(tag: str, folder: Path) -> tuple[str, list[dict]]:
    model, records = "?", []
    for stem, _ in SETS:
        path = folder / f"{stem}_{tag}.json"
        if not path.exists():
            raise SystemExit(f"ไม่พบ {path}")
        data = json.loads(path.read_text(encoding="utf-8"))
        model = data["config"]["chat_model"]
        records += [{**r, "set": stem} for r in data["records"]]
    return model, records


def pct(xs: list[float], p: float) -> float:
    xs = sorted(xs)
    return xs[min(len(xs) - 1, round(p * (len(xs) - 1)))]


def main():
    tags = sys.argv[1:] or ["7b", "3b"]
    folder = ROOT / "outputs"
    if not any(folder.glob(f"eval_report*_{tags[0]}.json")):
        folder = ROOT / "results" / "latency"
    console = Console()
    runs = {tag: load(tag, folder) for tag in tags}

    t = Table(title=f"ความแม่น (รวม 3 ชุด) — จาก {folder.relative_to(ROOT)}")
    t.add_column("ตัวชี้วัด")
    for tag, (model, _) in runs.items():
        t.add_column(model, justify="right")

    def frac(key):
        def f(recs):
            vals = [r[key] for r in recs if r[key] is not None]
            return f"{sum(vals)}/{len(vals)}"
        return f

    rows = [
        ("ตัดสินใจถูก (รวม)", frac("outcome_ok")),
        *[(f"  {label}", (lambda stem: lambda recs: frac("outcome_ok")([r for r in recs if r["set"] == stem]))(stem))
          for stem, label in SETS],
        ("ข้อเท็จจริงครบ", frac("content_ok")),
        ("Router: intent ถูก", frac("intent_ok")),
        ("ควรเปิด Ticket แต่ไปตอบ", lambda recs: str(sum(r["expected"]["outcome"] == "ticket" and r["actual"]["outcome"] == "answer" for r in recs))),
        ("ควรตอบได้แต่เปิด Ticket", lambda recs: str(sum(r["expected"]["outcome"] == "answer" and r["actual"]["outcome"] == "ticket" for r in recs))),
    ]
    for label, fn in rows:
        t.add_row(label, *[fn(recs) for _, recs in runs.values()])
    console.print(t)

    s = Table(title="เวลาต่อคำถาม (วินาที) และงานของโมเดล")
    s.add_column("ตัวชี้วัด")
    for model, _ in runs.values():
        s.add_column(model, justify="right")
    lat = {tag: [r["latency_s"] for r in recs] for tag, (_, recs) in runs.items()}
    s.add_row("เฉลี่ย", *[f"{statistics.mean(v):.2f}" for v in lat.values()])
    s.add_row("มัธยฐาน", *[f"{statistics.median(v):.2f}" for v in lat.values()])
    s.add_row("p90", *[f"{pct(v, 0.9):.2f}" for v in lat.values()])
    s.add_row("ช้าสุด", *[f"{max(v):.2f}" for v in lat.values()])

    def per_q(recs, key, stage=None):
        return statistics.mean(sum(st[key] for name, st in r["stages"].items() if stage in (None, name)) for r in recs)

    s.add_row("เรียกโมเดลต่อคำถาม", *[f"{per_q(recs, 'chat_calls'):.2f}" for _, recs in runs.values()])
    s.add_row("token อ่าน / สร้าง", *[f"{per_q(recs, 'prompt_tokens'):.0f} / {per_q(recs, 'output_tokens'):.0f}" for _, recs in runs.values()])
    s.add_row("prefill / decode (s)", *[f"{per_q(recs, 'prefill_ms') / 1000:.2f} / {per_q(recs, 'decode_ms') / 1000:.2f}" for _, recs in runs.values()])
    s.add_row("ความเร็ว decode (token/s)", *[f"{per_q(recs, 'output_tokens') / (per_q(recs, 'decode_ms') / 1000):.0f}" for _, recs in runs.values()])
    for stage in STAGES:
        s.add_row(f"  {stage} (s เฉลี่ยต่อคำถาม)", *[f"{per_q(recs, 'ms', stage) / 1000:.2f}" for _, recs in runs.values()])
    console.print(s)

    if len(runs) == 2:
        (a, (ma, ra)), (b, (mb, rb)) = runs.items()
        diff = [(x["id"], x["question"], x["actual"]["outcome"], y["actual"]["outcome"], x["expected"]["outcome"])
                for x, y in zip(ra, rb) if x["actual"]["outcome"] != y["actual"]["outcome"]]
        d = Table(title=f"ข้อที่ {ma} กับ {mb} ตัดสินใจต่างกัน ({len(diff)} ข้อ)")
        for col in ["id", "คำถาม", ma, mb, "เฉลย"]:
            d.add_column(col)
        for row in diff:
            d.add_row(row[0], row[1][:34], *row[2:])
        console.print(d)


if __name__ == "__main__":
    main()
