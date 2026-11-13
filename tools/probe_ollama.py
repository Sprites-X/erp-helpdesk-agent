"""วัดเวลาที่ใช้แค่ "ต่อถึง Ollama" แยกจากเวลาที่โมเดลทำงาน

ที่มา: ตารางเวลาแยกขั้นของ eval.py แสดงว่าแต่ละการเรียกโมเดลใช้เวลาจริงนานกว่าที่ Ollama รายงานไว้ราว 2 วินาที
สคริปต์นี้เรียก /api/version (ไม่มีงานของโมเดลเลย) ผ่านชื่อ localhost และผ่าน 127.0.0.1 แล้วเทียบเวลา

รัน: python tools/probe_ollama.py
"""
import socket
import statistics
import time
import urllib.request

PORT = 11434
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def timed(url: str, n: int = 5) -> list[float]:
    out = []
    for _ in range(n):
        t0 = time.perf_counter()
        try:
            with opener.open(url, timeout=10) as r:
                r.read()
            out.append((time.perf_counter() - t0) * 1000)
        except OSError as e:
            print(f"  {url}: เรียกไม่สำเร็จ ({e})")
            return out
    return out


def main():
    order = [ai[4][0] for ai in socket.getaddrinfo("localhost", PORT, type=socket.SOCK_STREAM)]
    print(f"ชื่อ localhost แปลงเป็นที่อยู่ตามลำดับนี้: {order}")
    for host in ["localhost", "127.0.0.1", "[::1]"]:
        ms = timed(f"http://{host}:{PORT}/api/version")
        if ms:
            print(f"  {host:10s} มัธยฐาน {statistics.median(ms):8.1f} ms  (ทุกครั้ง: {', '.join(f'{x:.0f}' for x in ms)})")


if __name__ == "__main__":
    main()
