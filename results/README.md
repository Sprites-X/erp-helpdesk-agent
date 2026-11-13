# ผลการรันจริง

รันบน RTX 5060 ด้วย `qwen2.5:7b` + `bge-m3` (ไฟล์ระดับบนสุดรันเมื่อ 12 พ.ย. 2026 ก่อนแก้เรื่องเวลาและกฎหลักฐาน)

| ไฟล์ | คืออะไร |
|---|---|
| `all3_log.txt` | ผล `eval.py` ของระบบเวอร์ชันปัจจุบันบนคำถามทั้ง 3 ชุด |
| `eval_set*.json` | ผลรายข้อของแต่ละชุด (คำตอบ เอกสารที่ค้นได้ คะแนน เวลา) |
| `experiment_sets1-2.txt`, `experiment_set3.txt` | ผลเทียบวิธีของขั้นตอบ 4 แบบ (`tools/experiment.py`) |
| `experiment_*.json` | คำตอบดิบของโมเดลในแต่ละวิธี |
| `history/` | log ของแต่ละรอบระหว่างปรับระบบ รวมรอบที่ลองแล้วแย่ลง |
| `latency_localhost/` | 13 พ.ย.: เวลาแยกขั้นของ 7B และ 3B ตอนยังต่อ Ollama ผ่าน `localhost` (ช้ากว่าที่ควรราว 2 วินาทีต่อการเรียก) |
| `latency/` | รอบเดียวกันหลังเปลี่ยนเป็น `127.0.0.1` พร้อมผลของ `tools/probe_ollama.py` และ `tools/compare_reports.py` |
| `evidence/` | 13 พ.ย.: กฎหลักฐานแบบเดิม (`_ev0`) เทียบกับแบบไม่นับหัวเรื่อง (`_ev1`, ค่าตั้งปัจจุบัน) มีประโยคหลักฐานของทุกข้อ |
| `external/` | 13 พ.ย.: ผลรันครั้งเดียวบนชุดคำถาม 20 ข้อที่ Gemini เขียน (`data/eval/external_gemini.jsonl`) ระบบไม่เคยเห็นคำถามชุดนี้มาก่อน |

ลำดับใน `history/`: `heldout_log_before` (ชุด 2 ครั้งแรก 18/22) → `both_log_router_prompt_attempt` → `seeds_log` →
`both_log_before_agentic` → `both_log_agentic_v1_failed` → `both_log` → `all3_log_fewshot_version` (ชุด 3 ครั้งแรก 19/22)
