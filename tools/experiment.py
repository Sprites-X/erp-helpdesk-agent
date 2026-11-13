"""ทดลองเทียบวิธีทำ Knowledge agent 4 แบบบนคำถามชุดเดียวกัน (ablation)

แนวคิด: ตรึงผลของ Router กับ Retriever ไว้ (cache) แล้วเปลี่ยนเฉพาะขั้น "ตอบ" จะได้รู้ว่าผลต่างมาจากขั้นนี้จริง
  A = กติกาอย่างเดียว (ให้โมเดลบอกเองว่า grounded ไหม)
  B = A + ตัวอย่าง (few-shot)
  C = ให้โมเดลคัดลอก "ประโยคหลักฐาน" จากเอกสารก่อนตอบ แล้วโค้ดตรวจว่าประโยคนั้นมีอยู่จริงในเอกสาร  ← วิธีที่ใช้อยู่ในระบบ
  D = C + ตัวอย่าง

รัน: python tools/experiment.py data/eval/questions.jsonl data/eval/heldout.jsonl
"""
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from helpdesk import config  # noqa: E402
from helpdesk.agents import knowledge as K  # noqa: E402
from helpdesk.agents.router import route  # noqa: E402
from helpdesk.index import search  # noqa: E402
from helpdesk.llm import LLMError, chat_json  # noqa: E402
from helpdesk.modules import ERROR_CODE  # noqa: E402

# ตัวอย่างใช้โมดูลสมมติ (ใบลา) ที่ไม่มีในคู่มือจริง เพื่อไม่ให้เฉลยของชุดทดสอบรั่วเข้า prompt
FEWSHOT_C = f'''

ตัวอย่างที่ 1
CONTEXT:
{K._EX_DOCS}
ข้อความจากผู้ใช้: หยุดพักผ่อนได้กี่วันต่อปี
ผลลัพธ์: {{"evidence": "ลาพักร้อนได้ปีละ 10 วัน", "doc_id": "HR-3", "answer": "ลาพักร้อนได้ปีละ 10 วัน"}}

ตัวอย่างที่ 2
CONTEXT:
{K._EX_DOCS}
ข้อความจากผู้ใช้: กดส่งใบลาแล้วหน้าจอดับ
ผลลัพธ์: {{"evidence": "", "doc_id": "", "answer": ""}}'''
def run_variant(name: str, question: str, intent: str, hits: list[dict]) -> dict:
    user = f"CONTEXT:\n{K.format_context(hits)}\n\nประเภท: {intent}\nข้อความจากผู้ใช้: {question}"
    try:
        if name in "AB":
            out = chat_json(K.SYSTEM_RULES + (K.FEWSHOT if name == "B" else ""), user, K.SCHEMA)
            grounded = bool(out.get("grounded")) and bool(out.get("answer", "").strip())
        else:
            out = chat_json(K.evidence_system() + (FEWSHOT_C if name == "D" else ""), user, K.SCHEMA_EVIDENCE)
            found = K.evidence_in_docs(out.get("evidence", ""), hits)
            out["evidence_verified_in"] = found
            grounded = found is not None and bool(out.get("answer", "").strip())
        return {"grounded": grounded, "answer": out.get("answer", "") if grounded else "", "raw": out}
    except LLMError as e:
        return {"grounded": False, "answer": "", "raw": {"error": str(e)}}


def main():
    files = [Path(a) for a in sys.argv[1:]] or [config.EVAL_FILE]
    out_dir = ROOT / "outputs"
    out_dir.mkdir(exist_ok=True)
    cache_file = out_dir / "exp_cache.json"
    cache = json.loads(cache_file.read_text(encoding="utf-8")) if cache_file.exists() else {}
    log = open(ROOT / "experiment_log.txt", "w", encoding="utf-8")

    def say(*a):
        print(*a); print(*a, file=log, flush=True)

    items = []
    for f in files:
        for line in f.read_text(encoding="utf-8").splitlines():
            if line.strip():
                items.append({**json.loads(line), "set": f.stem})

    # 1) Router + Retriever (ตรึงไว้ใน cache)
    for it in items:
        if it["id"] in cache:
            continue
        r, _ = route(it["question"])
        module = r["module"]
        hits = search(r["rewritten_query"], module)
        if module not in ("GENERAL", "UNKNOWN"):
            merged = {h["id"]: h for h in hits + search(r["rewritten_query"], None)}
            hits = sorted(merged.values(), key=lambda h: h["score"], reverse=True)[:config.TOP_K + 2]
        raw_hits = search(it["question"], None)
        cache[it["id"]] = {"router": r, "hits": hits, "raw_top": raw_hits[0]["score"], "raw_top_id": raw_hits[0]["id"]}
        cache_file.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")

    say("== ขอบเขต: intent ของ Router เทียบกับคะแนนค้นด้วยคำถามดิบ (ทุกโมดูล) ==")
    for it in items:
        c = cache[it["id"]]
        if it["outcome"] == "out_of_scope" or c["router"]["intent"] == "out_of_scope" or it["outcome"] == "ticket":
            say(f"{it['id']} คาด={it['outcome']:12s} router={c['router']['intent']:12s} module={c['router']['module']:8s} "
                f"raw_top={c['raw_top']:.3f} ({c['raw_top_id']}) routed_top={c['hits'][0]['score']:.3f}")

    # 2) เทียบ 4 วิธีของขั้นตอบ
    results = {}
    for v in "ABCD":
        t0 = time.perf_counter()
        rows = []
        for it in items:
            c = cache[it["id"]]
            if it["outcome"] == "out_of_scope":
                continue
            codes = {m.group(0).upper() for m in ERROR_CODE.finditer(it["question"])}
            if codes and not any(code in h["text"].upper() for h in c["hits"] for code in codes):
                res = {"grounded": False, "answer": "", "raw": {"rule": "unknown error code"}}
            else:
                res = run_variant(v, it["question"], it["intent"], c["hits"])
            rows.append({"id": it["id"], "set": it["set"], "expected": it["outcome"], "grounded": res["grounded"],
                         "content_ok": res["grounded"] and all(k in res["answer"] for k in it["must_include"]),
                         "answer": res["answer"], "raw": res["raw"]})
        results[v] = rows
        (out_dir / "experiment.json").write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
        say(f"\n== วิธี {v} ({time.perf_counter() - t0:.0f} วินาที) ==")
        for s in sorted({r["set"] for r in rows}):
            ans = [r for r in rows if r["set"] == s and r["expected"] == "answer"]
            tic = [r for r in rows if r["set"] == s and r["expected"] == "ticket"]
            say(f"[{s}] ควรตอบ: ตอบได้ {sum(r['grounded'] for r in ans)}/{len(ans)} เนื้อหาครบ {sum(r['content_ok'] for r in ans)}/{len(ans)} | "
                f"ควรเปิด Ticket: ตอบมั่ว {sum(r['grounded'] for r in tic)}/{len(tic)}")
        say("  ควรตอบแต่ไม่ตอบ:", [r["id"] for r in rows if r["expected"] == "answer" and not r["grounded"]])
        say("  ตอบแต่เนื้อหาไม่ครบ:", [r["id"] for r in rows if r["expected"] == "answer" and r["grounded"] and not r["content_ok"]])
        say("  ตอบมั่ว:", [r["id"] for r in rows if r["expected"] == "ticket" and r["grounded"]])
    say("\nDONE")


if __name__ == "__main__":
    main()
