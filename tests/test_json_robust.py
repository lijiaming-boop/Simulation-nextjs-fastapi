import json
import re

def robust(text):
    if not text: return None
    text = text.strip()
    try: return json.loads(text)
    except: pass
    start, end = text.find("{"), text.rfind("}") + 1
    if start >= 0 and end > start:
        try: return json.loads(text[start:end])
        except: pass
    clean = re.sub(r"```(?:json)?\s*", "", text).replace("```", "")
    start, end = clean.find("{"), clean.rfind("}") + 1
    if start >= 0 and end > start:
        try: return json.loads(clean[start:end])
        except: pass
    if start >= 0 and end > start:
        js = text[start:end]
        js = re.sub(r",\s*}", "}", js)
        js = re.sub(r",\s*]", "]", js)
        try: return json.loads(js)
        except: pass
    return None

# Test
print("1:", robust('{"a":1}'))
print("2:", robust('text {"a":1} end'))
print("3:", robust('```json\n{"a":1}\n```'))
print("4:", robust('{"a":1,}'))
print("5:", robust("not json"))
