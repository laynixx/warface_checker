import re
import math
import base64
import io
import ctypes
import js2py
from PIL import Image
from core.utils import console_log

class WarfaceBypass:
    @staticmethod
    def int32(val: int) -> int:
        return (val & 0xFFFFFFFF) - 0x100000000 if val & 0x80000000 else val & 0xFFFFFFFF

    @staticmethod
    def parse_jsfuck_number(expr: str, tag: str = "BYPASS") -> int:
        expr = expr.strip()
        try:
            val = js2py.eval_js(expr)
            if val is not None:
                return int(float(val))
        except Exception as e:
            console_log(tag, f" js2py eval failed: {e}")
        raise RuntimeError("Не удалось вычислить JSFuck-выражение")

    @classmethod
    def solve_njs_from_script(cls, script_code: str, tag: str = "BYPASS") -> dict:
        n_js_t_match = re.search(r"d\.cookie\s*=\s*'n_js_t=(\d+)", script_code)
        if not n_js_t_match:
            raise RuntimeError("Не удалось найти n_js_t в скрипте")
        n_js_t_val = n_js_t_match.group(1)

        t_match = re.search(r'var\s+t\s*=\s*(.+?);\s*var\s+e\s*=', script_code, re.DOTALL)
        if not t_match:
            raise RuntimeError("Не найдено выражение для t")
        jsfuck_t = t_match.group(1).strip()

        t_val = cls.parse_jsfuck_number(jsfuck_t, tag)

        img_match = re.search(r"m\.src\s*=\s*'data:image/png;base64,([^']+)'", script_code)
        if not img_match:
            raise RuntimeError("Не найдена canvas-картинка")
        img_b64 = img_match.group(1)

        def asm_a(n: int) -> int:
            t_local = ctypes.c_int32(int(math.sqrt(float(n)))).value
            i = 3
            while i < t_local:
                if float(n) % float(i) == 0.0:
                    t_local = ctypes.c_int32(int(float(n) / float(i) + float(i))).value
                    break
                i += 2
            return t_local

        t_final = asm_a(t_val)
        img_data = base64.b64decode(img_b64)
        img = Image.open(io.BytesIO(img_data))
        pixels = img.load()

        h = 0
        for i in range(31, -1, -1):
            r = pixels[i, 0][0]
            h = cls.int32(h * 2)
            if r > 0:
                h = cls.int32(h + 1)

        h = cls.int32(h ^ t_final)
        if h < 0:
            h += 4294967296

        return {"n_js_t": n_js_t_val, "n_js_d": str(h)}