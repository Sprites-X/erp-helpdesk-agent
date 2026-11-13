"""ขั้นที่ 3: วัดผลระบบด้วยชุดคำถามทดสอบ data/eval/questions.jsonl

วัด 5 อย่าง:
  - Router: จัดประเภทคำถาม (intent) และโมดูลถูกไหม
  - Retrieval hit@k: เอกสารที่ควรเจออยู่ใน top-k ไหม
  - Outcome: ตัดสินใจถูกไหมว่าจะตอบ / เปิด Ticket / ปฏิเสธ
  - Content: คำตอบมีข้อเท็จจริงสำคัญครบไหม (เช็ก keyword)
  - Latency รวม และแยกตามขั้น (เวลา, จำนวนครั้งที่เรียกโมเดล, token ที่อ่าน/สร้าง)

ก่อนจับเวลาจะรันคำถามอุ่นเครื่อง 1 ข้อ (ไม่นับผล) เพื่อไม่ให้เวลาโหลดโมเดลปนกับเวลาตอบ

รัน:  python eval.py                        วัดผลชุด 1 (ไม่บันทึก Ticket จริง)
      python eval.py --file <ไฟล์.jsonl>     วัดชุดอื่น
      python eval.py --sweep                แสดงผลถ้าเปลี่ยนค่า MIN_SCORE ใช้ช่วยเลือก threshold
      python eval.py --tag 3b               ต่อท้ายชื่อไฟล์ผล ใช้ตอนเทียบหลายโมเดล
"""
import argparse
import json
import time
from pathlib import Path

from rich.console import Console
from rich.table import Table

from helpdesk import config
from helpdesk.graph import run
from helpdesk.llm import LLMError

console = Console()


def mark(v) -> str:
    return "-" if v is None else ("[green]✓[/green]" if v else "[red]✗[/red]")


def rate(values) -> tuple[int, int]:
    vals = [v for v in values if v is not None]
    return sum(vals), len(vals)


USAGE_KEYS = ["chat_calls", "prompt_tokens", "output_tokens", "prefill_ms", "decode_ms", "load_ms", "embed_ms"]


def stage_usage(trace: list[dict]) -> dict:
    """รวมเวลาและการใช้โมเดลของแต่ละขั้น (ขั้นเดียวกันอาจทำงาน 2 รอบเมื่อมีการค้นซ้ำ)"""
    out: dict[str, dict] = {}
    for step in trace:
        agg = out.setdefault(step["agent"], {"ms": 0, **{k: 0 for k in USAGE_KEYS}})
        agg["ms"] += step["ms"]
        for k in USAGE_KEYS:
            agg[k] += step.get("llm", {}).get(k, 0)
    return out


def stage_table(records: list[dict]) -> tuple[Table, dict]:
    n = len(records)
    agents = [a for a in ["Router", "Retriever", "Knowledge", "Ticket"] if any(a in r["stages"] for r in records)]
    t = Table(title=f"เวลาแยกตามขั้น (เฉลี่ยต่อคำถาม จาก {n} ข้อ)")
    for col in ["ขั้น", "ทำงานใน", "เวลา ms", "เรียกโมเดล", "token อ่าน", "token สร้าง", "prefill ms", "decode ms", "สัดส่วนเวลา"]:
        t.add_column(col, justify="left" if col == "ขั้น" else "right")
    total_ms = sum(st["ms"] for r in records for st in r["stages"].values()) or 1
    summary = {}
    for a in agents + ["รวม"]:
        rows = [r["stages"][a] for r in records if a in r["stages"]] if a != "รวม" else \
               [{k: sum(st[k] for st in r["stages"].values()) for k in ["ms", *USAGE_KEYS]} for r in records]
        avg = {k: sum(x[k] for x in rows) / n for k in ["ms", *USAGE_KEYS]}
        summary[a] = {"questions": len(rows), **{k: round(v, 1) for k, v in avg.items()}}
        share = sum(x["ms"] for x in rows) / total_ms
        t.add_row(a, f"{len(rows)}/{n}", f"{avg['ms']:.0f}", f"{avg['chat_calls']:.2f}", f"{avg['prompt_tokens']:.0f}",
                  f"{avg['output_tokens']:.0f}", f"{avg['prefill_ms']:.0f}", f"{avg['decode_ms']:.0f}", f"{share:.0%}")
    return t, summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sweep", action="store_true")
    parser.add_argument("--file", default=str(config.EVAL_FILE), help="ไฟล์ชุดคำถาม (.jsonl)")
    parser.add_argument("--tag", default="", help="ต่อท้ายชื่อไฟล์ผล เช่น ชื่อโมเดล")
    parser.add_argument("--no-warmup", action="store_true", help="ไม่รันคำถามอุ่นเครื่องก่อนจับเวลา")
    args = parser.parse_args()

    eval_file = Path(args.file)
    name = "eval_report" if eval_file == config.EVAL_FILE else f"eval_report_{eval_file.stem}"
    report_file = config.EVAL_REPORT.with_name(name + (f"_{args.tag}" if args.tag else "") + ".json")
    items = [json.loads(l) for l in eval_file.read_text(encoding="utf-8-sig").splitlines() if l.strip()]
    records = []
    with console.status("กำลังรันชุดทดสอบ...") as status:
        if config.BACKEND != "stub" and not args.no_warmup:
            status.update("อุ่นเครื่อง: โหลดโมเดลเข้า GPU (ไม่นับผล)")
            try:
                run("PO อนุมัติแล้วแก้ไขยังไง", save_ticket=False)
            except (LLMError, RuntimeError) as e:
                console.print(f"[red]หยุดการทดสอบ:[/red] {e}")
                raise SystemExit(1)
        for i, item in enumerate(items, 1):
            status.update(f"กำลังรัน {i}/{len(items)}: {item['question'][:40]}")
            t0 = time.perf_counter()
            try:
                st = run(item["question"], save_ticket=False)
            except (LLMError, RuntimeError) as e:
                console.print(f"[red]หยุดการทดสอบ:[/red] {e}")
                raise SystemExit(1)
            latency = time.perf_counter() - t0
            hit_ids = [h["id"].split("#")[0] for h in st.get("hits", [])]
            reply = st.get("reply", "")
            records.append({
                "id": item["id"],
                "question": item["question"],
                "expected": {k: item[k] for k in ("intent", "module", "outcome")},
                "actual": {"intent": st.get("intent"), "module": st.get("module"), "outcome": st.get("outcome")},
                "intent_ok": st.get("intent") == item["intent"],
                "module_ok": None if item["intent"] == "out_of_scope" else st.get("module") == item["module"],
                "retrieval_ok": (any(s in hit_ids for s in item["expected_sources"]) if item["expected_sources"] else None),
                "outcome_ok": st.get("outcome") == item["outcome"],
                "content_ok": (st.get("outcome") == "answer" and all(k in reply for k in item["must_include"])
                               if item["must_include"] else None),
                "top_score": st.get("top_score"),
                "searches": len(st.get("tried_queries", [])),
                "queries": st.get("tried_queries", []),
                "hits": hit_ids,
                "reply": reply,
                "evidence": st.get("evidence", ""),
                "latency_s": round(latency, 2),
                "stages": stage_usage(st.get("trace", [])),
            })

    t = Table(title=f"ผลรายข้อ [{eval_file.name}{' · ' + args.tag if args.tag else ''}] (backend={config.BACKEND}, model={config.CHAT_MODEL}, MIN_SCORE={config.MIN_SCORE}, seed={config.SEED})")
    for col in ["id", "คำถาม", "intent", "โมดูล", "เจอเอกสาร", "ผลลัพธ์ (คาด→จริง)", "เนื้อหา", "top score", "วินาที"]:
        t.add_column(col)
    for r in records:
        exp, act = r["expected"]["outcome"], r["actual"]["outcome"]
        outcome = f"{exp}" if exp == act else f"[red]{exp}→{act}[/red]"
        score = f"{r['top_score']:.3f}" if r["top_score"] is not None else "-"
        t.add_row(r["id"], r["question"][:30], mark(r["intent_ok"]), mark(r["module_ok"]), mark(r["retrieval_ok"]),
                  outcome, mark(r["content_ok"]), score, f"{r['latency_s']:.1f}")
    console.print(t)

    summary = {}
    s = Table(title="สรุป")
    s.add_column("ตัวชี้วัด")
    s.add_column("ผล", justify="right")
    for key, label in [("intent_ok", "Router: intent ถูก"), ("module_ok", "Router: โมดูลถูก"),
                       ("retrieval_ok", "Retrieval: เอกสารที่ถูกอยู่ในชุดที่ส่งให้ Knowledge agent"), ("outcome_ok", "ตัดสินใจ ตอบ/Ticket/ปฏิเสธ ถูก"),
                       ("content_ok", "คำตอบมีข้อเท็จจริงสำคัญครบ")]:
        ok, n = rate(r[key] for r in records)
        summary[key] = {"correct": ok, "total": n}
        s.add_row(label, f"{ok}/{n} ({ok / n:.0%})" if n else "-")
    false_answer = sum(r["expected"]["outcome"] == "ticket" and r["actual"]["outcome"] == "answer" for r in records)
    false_ticket = sum(r["expected"]["outcome"] == "answer" and r["actual"]["outcome"] == "ticket" for r in records)
    lat = sorted(r["latency_s"] for r in records)
    summary |= {"answered_but_should_ticket": false_answer, "ticket_but_should_answer": false_ticket,
                "latency_avg_s": round(sum(lat) / len(lat), 2), "latency_max_s": lat[-1]}
    re_searched = [r for r in records if r["searches"] > 1]
    summary["re_searched"] = len(re_searched)
    summary["re_searched_then_answered_correctly"] = sum(r["outcome_ok"] and r["actual"]["outcome"] == "answer" for r in re_searched)
    s.add_row("Knowledge agent ขอค้นซ้ำเอง (แล้วตอบถูก)", f"{summary['re_searched']} ({summary['re_searched_then_answered_correctly']})")
    s.add_row("[red]ควรเปิด Ticket แต่ไปตอบ (เสี่ยงตอบมั่ว)", str(false_answer))
    s.add_row("ควรตอบได้แต่เปิด Ticket", str(false_ticket))
    s.add_row("เวลาเฉลี่ย / ช้าสุด", f"{summary['latency_avg_s']:.2f} / {summary['latency_max_s']:.2f} วินาที")
    console.print(s)
    if config.BACKEND != "stub":
        stages, summary["stages"] = stage_table(records)
        console.print(stages)
        console.print("[dim]prefill = เวลาอ่าน prompt, decode = เวลาสร้างคำตอบทีละ token; ส่วนที่เหลือของเวลาคือค้นเอกสาร embedding และ overhead[/dim]")

    if args.sweep:
        sw = Table(title="ถ้าเปลี่ยน MIN_SCORE (ประมาณจาก top score ของรอบนี้ ดูเฉพาะด่านคัดกรองก่อน Knowledge agent)")
        for col in ["MIN_SCORE", "ด่านคัดกรองถูก", "ปล่อยข้อที่ควรเปิด Ticket ผ่านไป", "กันข้อที่ควรตอบได้ทิ้ง"]:
            sw.add_column(col, justify="right")
        scored = [r for r in records if r["expected"]["outcome"] in ("answer", "ticket") and r["top_score"] is not None]
        for x in range(20, 75, 5):
            th = x / 100
            leak = sum(r["expected"]["outcome"] == "ticket" and r["top_score"] >= th for r in scored)
            block = sum(r["expected"]["outcome"] == "answer" and r["top_score"] < th for r in scored)
            sw.add_row(f"{th:.2f}", f"{len(scored) - leak - block}/{len(scored)}", str(leak), str(block))
        console.print(sw)
        console.print("[dim]ข้อที่ 'ปล่อยผ่านไป' ยังมี Knowledge agent ตรวจอีกชั้น จึงเลือกค่าที่ 'กันข้อที่ควรตอบได้ทิ้ง' ใกล้ 0 ไว้ก่อน[/dim]")

    report_file.parent.mkdir(parents=True, exist_ok=True)
    report_file.write_text(json.dumps({"config": {"backend": config.BACKEND, "chat_model": config.CHAT_MODEL,
                                                         "embed_model": config.EMBED_MODEL, "min_score": config.MIN_SCORE,
                                                         "top_k": config.TOP_K},
                                              "summary": summary, "records": records}, ensure_ascii=False, indent=2),
                                  encoding="utf-8")
    console.print(f"[dim]บันทึกผลละเอียดที่ {report_file.relative_to(config.ROOT)}[/dim]")


if __name__ == "__main__":
    main()
