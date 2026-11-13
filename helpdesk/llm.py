"""คุยกับ Ollama (chat แบบบังคับ JSON + embedding) และ embedding สำรองสำหรับ stub mode"""
import http.client
import json
import math
import re
import time
import urllib.error
import urllib.request
import zlib

from . import config


class LLMError(RuntimeError):
    pass


# ไม่ผ่าน proxy ของระบบ เพราะ Ollama รันอยู่บนเครื่องตัวเอง
_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

# บันทึกเวลาและจำนวน token ของทุกการเรียก Ollama เพื่อดูว่าเวลาหมดไปที่ขั้นไหน
# Ollama ส่งเวลาแยกมาให้ (หน่วย nanosecond): prefill = อ่าน prompt, decode = สร้างคำตอบทีละ token
_calls: list[dict] = []


def _stats(kind: str, data: dict, wall_s: float) -> dict:
    def ms(key: str) -> float:
        return round(data.get(key, 0) / 1e6, 1)
    return {"kind": kind, "wall_ms": round(wall_s * 1000, 1), "load_ms": ms("load_duration"),
            "prompt_tokens": data.get("prompt_eval_count", 0), "prefill_ms": ms("prompt_eval_duration"),
            "output_tokens": data.get("eval_count", 0), "decode_ms": ms("eval_duration")}


def take_calls() -> list[dict]:
    """คืนสถิติของการเรียกโมเดลทั้งหมดตั้งแต่ครั้งก่อนที่เรียกฟังก์ชันนี้ แล้วล้างรายการ"""
    out = _calls[:]
    _calls.clear()
    return out


def _post(path: str, payload: dict, timeout: int = 180) -> dict:
    req = urllib.request.Request(
        config.OLLAMA_URL + path,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with _opener.open(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise LLMError(f"Ollama ตอบ {e.code}: {e.read().decode('utf-8', 'replace')[:300]}") from e
    except urllib.error.URLError as e:
        raise LLMError(f"เชื่อมต่อ Ollama ที่ {config.OLLAMA_URL} ไม่ได้ ({e}) — เปิด `ollama serve` แล้วหรือยัง") from e
    except (OSError, http.client.HTTPException) as e:
        # การเชื่อมต่อหลุดกลางทาง มักเกิดตอนโหลดโมเดลไม่ขึ้น (VRAM ไม่พอ) หรือ Ollama ล่ม
        raise LLMError(f"Ollama ตัดการเชื่อมต่อระหว่างทำงาน ({type(e).__name__}: {e}) — "
                       f"ดู log ของ Ollama หรือลองโมเดลที่เล็กลง") from e


def get(path: str, timeout: int = 10) -> dict:
    try:
        with _opener.open(config.OLLAMA_URL + path, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (OSError, http.client.HTTPException) as e:
        raise LLMError(f"เชื่อมต่อ Ollama ที่ {config.OLLAMA_URL} ไม่ได้ ({e})") from e


def parse_json(text: str) -> dict:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass
    raise LLMError(f"โมเดลตอบกลับไม่เป็น JSON: {text[:200]!r}")


def chat_json(system: str, user: str, schema: dict, temperature: float = 0.0) -> dict:
    """เรียกโมเดลแชตแล้วบังคับให้ตอบตาม JSON schema (Ollama structured outputs)"""
    t0 = time.perf_counter()
    data = _post("/api/chat", {
        "model": config.CHAT_MODEL,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "format": schema,
        "stream": False,
        "options": {"temperature": temperature, "seed": config.SEED, "num_predict": config.MAX_OUTPUT_TOKENS},
    })
    _calls.append(_stats("chat", data, time.perf_counter() - t0))
    return parse_json(data.get("message", {}).get("content", ""))


def embed(texts: list[str]) -> list[list[float]]:
    if config.BACKEND == "stub":
        return [hash_embed(t) for t in texts]
    vectors = []
    for i in range(0, len(texts), 32):
        t0 = time.perf_counter()
        data = _post("/api/embed", {"model": config.EMBED_MODEL, "input": texts[i:i + 32]})
        _calls.append(_stats("embed", data, time.perf_counter() - t0))
        vectors.extend(data["embeddings"])
    return vectors


def hash_embed(text: str, dim: int = 1024) -> list[float]:
    """embedding ปลอมจาก character n-gram (hashing trick) ไม่ต้องโหลดโมเดล ใช้ทดสอบ pipeline เท่านั้น"""
    t = re.sub(r"\s+", "", text.lower())
    vec = [0.0] * dim
    for n in (2, 3):
        for i in range(len(t) - n + 1):
            h = zlib.crc32(t[i:i + n].encode("utf-8"))
            vec[h % dim] += 1.0 if (h >> 16) & 1 else -1.0
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]
