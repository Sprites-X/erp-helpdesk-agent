"""ค่าตั้งต้นทั้งหมดของโปรเจกต์ เปลี่ยนได้ผ่าน environment variable"""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
PROCESSED_DIR = ROOT / "data" / "processed"
CHUNKS_FILE = PROCESSED_DIR / "chunks.jsonl"
PREP_REPORT = PROCESSED_DIR / "prep_report.json"
EVAL_FILE = ROOT / "data" / "eval" / "questions.jsonl"
CHROMA_DIR = ROOT / "storage" / "chroma"
TICKET_DIR = ROOT / "outputs" / "tickets"
EVAL_REPORT = ROOT / "outputs" / "eval_report.json"

# ollama = ใช้โมเดลจริงผ่าน Ollama | stub = กฎง่าย ๆ ไม่ต้องมี GPU ไว้เช็กว่า pipeline รันได้
BACKEND = os.getenv("LLM_BACKEND", "ollama").lower()
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434").rstrip("/")
CHAT_MODEL = os.getenv("CHAT_MODEL", "qwen2.5:7b")
EMBED_MODEL = os.getenv("EMBED_MODEL", "bge-m3")

COLLECTION = "erp_helpdesk_kb"
TOP_K = int(os.getenv("TOP_K", "4"))
# คะแนน cosine ขั้นต่ำของเอกสารอันดับ 1 ที่ถือว่า "เจอเรื่องที่เกี่ยวข้อง" ต่ำกว่านี้ส่งไปเปิด Ticket
# ค่าเริ่มต้นเป็นค่าประมาณ ให้ปรับจากผล `python eval.py --sweep`
MIN_SCORE = float(os.getenv("MIN_SCORE", "0.55" if BACKEND == "ollama" else "0.20"))
# seed ของโมเดลแชต ตั้งค่าเดิมเพื่อให้ผลซ้ำได้ เปลี่ยนค่าเพื่อดูว่าผลแกว่งแค่ไหน
SEED = int(os.getenv("SEED", "42"))
# จำนวนครั้งที่ Knowledge agent ขอค้นซ้ำด้วยคำค้นของตัวเองได้ ก่อนต้องส่งต่อ Ticket (0 = ปิดความสามารถนี้)
MAX_EXTRA_SEARCHES = int(os.getenv("MAX_EXTRA_SEARCHES", "1"))
# เพดานความยาวคำตอบของโมเดลต่อครั้ง กันโมเดลพิมพ์ไม่หยุดจนค้าง
MAX_OUTPUT_TOKENS = int(os.getenv("MAX_OUTPUT_TOKENS", "500"))
# ถ้า Router บอกว่านอกขอบเขต แต่คำถามตรงกับเอกสารในคลังด้วยคะแนนอย่างน้อยเท่านี้ ให้ถือว่าอยู่ในขอบเขต
SCOPE_RESCUE_SCORE = float(os.getenv("SCOPE_RESCUE_SCORE", "0.55" if BACKEND == "ollama" else "0.30"))
MAX_CHUNK_CHARS = 800
