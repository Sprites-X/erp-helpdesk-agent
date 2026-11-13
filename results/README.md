# ผลการรันจริง

รันเมื่อ 12 พ.ย. 2026 บน RTX 5060 ด้วย `qwen2.5:7b` + `bge-m3`

| ไฟล์ | คืออะไร |
|---|---|
| `all3_log.txt` | ผล `eval.py` ของระบบเวอร์ชันปัจจุบันบนคำถามทั้ง 3 ชุด |
| `eval_set*.json` | ผลรายข้อของแต่ละชุด (คำตอบ เอกสารที่ค้นได้ คะแนน เวลา) |
| `experiment_sets1-2.txt`, `experiment_set3.txt` | ผลเทียบวิธีของขั้นตอบ 4 แบบ (`tools/experiment.py`) |
| `experiment_*.json` | คำตอบดิบของโมเดลในแต่ละวิธี |
| `history/` | log ของแต่ละรอบระหว่างปรับระบบ รวมรอบที่ลองแล้วแย่ลง |

ลำดับใน `history/`: `heldout_log_before` (ชุด 2 ครั้งแรก 18/22) → `both_log_router_prompt_attempt` → `seeds_log` →
`both_log_before_agentic` → `both_log_agentic_v1_failed` → `both_log` → `all3_log_fewshot_version` (ชุด 3 ครั้งแรก 19/22)
