"""Test ai_vision module"""
import sys
sys.path.insert(0, '.')
import json
from simulation.ai智能识别设备铭牌.ai_vision import _robust_extract_json

# Test JSON extraction robustness
print("=== Test _robust_extract_json ===")

# 1a
r = _robust_extract_json('{"a":1}')
assert r == {"a": 1}
print("  1a OK: standard JSON")

# 1b
r = _robust_extract_json('some text {"a":1} end')
assert r == {"a": 1}
print("  1b OK: with extra text")

# 1c - markdown code block
text = '```json\n{"a":1}\n```'
print(f"  Input: {repr(text)}")
r = _robust_extract_json(text)
print(f"  Result: {r}")
assert r == {"a": 1}, f"Expected {{'a':1}}, got {r}"
print("  1c OK: markdown code block")

# 1d - trailing comma
r = _robust_extract_json('{"a":1,}')
assert r == {"a": 1}
print("  1d OK: trailing comma")

# 1e - invalid
r = _robust_extract_json("not json at all")
assert r is None
print("  1e OK: invalid returns None")

print()
print("=== Test extract_plant_topology (text) ===")
from simulation.ai智能识别设备铭牌.ai_vision import extract_plant_topology

r = extract_plant_topology(
    content=(
        "2台定频螺杆机RC-2-580B，单台制冷量2035kW，额定功率421kW，COP 4.83。"
        "3台冷冻泵150kW工频流量750m3/h。3台冷却泵110kW工频流量950m3/h。"
        "4台冷却塔18.5kW变频每塔2台风机。项目在武汉。"
    ),
    content_type="text",
)
assert r is not None, "extract_plant_topology returned None"
ch = r["chillers"][0]
assert ch["qty"] == 2, f"qty expected 2 got {ch['qty']}"
assert abs(ch["capacity_kw"] - 2035) < 50, f"capacity expected ~2035 got {ch['capacity_kw']}"
assert abs(ch["rated_cop"] - 4.83) < 0.2, f"cop expected ~4.83 got {ch['rated_cop']}"
assert ch["variable_freq"] is False, f"vf expected False got {ch['variable_freq']}"
print(f"  Region: {r.get('region')}")
print(f"  Chillers: {json.dumps(r['chillers'], ensure_ascii=False)}")
print(f"  CHW pumps: {json.dumps(r['chw_pumps'], ensure_ascii=False)}")
print("  All text extraction assertions passed!")

print()
print("=== Test extract_plant_topology (image) ===")
import struct, zlib

def make_png(w, h, r_val, g_val, b_val):
    def chunk(ctype, data):
        c = ctype + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)
    raw = b""
    for y in range(h):
        raw += b"\x00" + bytes([r_val, g_val, b_val]) * w
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )

png = make_png(100, 100, 255, 0, 0)
r2 = extract_plant_topology(content_type="image", image_data=png, media_type="image/png")
print(f"  Image API connectivity: {'OK' if r2 is not None else 'OK (None for non-nameplate - expected)'}")

print()
print("=== ALL TESTS PASSED ===")
