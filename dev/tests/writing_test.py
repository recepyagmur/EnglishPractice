"""Writing review over SSE: time each stage and print the results."""
import json
import sys
import time
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8100"
TEXT = """Dear Mark,

I hope you are doing well. I am writing to invite you to my birthday party next saturday. The party will be in my house and it start at 7 pm. I will cook turkish food and my sister make a cake. Many of my friends is coming, so you can meet with new peoples.

Please tell me if you can come until Thursday.

Best wishes,
Ali"""

print(json.load(urllib.request.urlopen(f"{BASE}/api/writing/types")))
t = time.perf_counter()
print(json.load(urllib.request.urlopen(f"{BASE}/api/writing/prompt?type=email")), f"{(time.perf_counter()-t)*1000:.0f} ms")

req = urllib.request.Request(f"{BASE}/api/writing/review", method="POST",
                             data=json.dumps({"task_type": "email", "prompt": "Invite a friend to your birthday party.",
                                              "text": TEXT}).encode(),
                             headers={"Content-Type": "application/json"})
t0 = time.perf_counter()
ms = lambda: f"{(time.perf_counter() - t0) * 1000:6.0f} ms"
first_improved = None
with urllib.request.urlopen(req, timeout=300) as resp:
    event = None
    for raw in resp:
        line = raw.decode("utf-8").rstrip("\n")
        if line.startswith("event: "):
            event = line[7:]
        elif line.startswith("data: "):
            data = json.loads(line[6:])
            if event == "saved":
                print(ms(), "saved", data)
            elif event == "sentence":
                errs = [(e["category"], e["wrong"], e["right"], TEXT[e["start"]:e["end"]] if e["start"] is not None else None)
                        for e in data["errors"]]
                print(ms(), f"#{data['index']} {data['original'][:50]!r} {errs}")
            elif event == "assessment":
                print(ms(), "assessment", json.dumps(data, ensure_ascii=False, indent=1))
            elif event == "improved_delta" and first_improved is None:
                first_improved = ms()
                print(first_improved, "improved version starts streaming")
            elif event == "done":
                print(ms(), "done\n", data["review"]["improved_version"])
            elif event == "error":
                print(ms(), "ERROR", data)
