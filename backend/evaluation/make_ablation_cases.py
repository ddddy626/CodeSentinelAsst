"""Build a fixed synthetic comparison set with long-context cases."""

import json
from pathlib import Path

directory = Path(__file__).parent
cases = json.loads((directory / "cases.json").read_text(encoding="utf-8"))
padding = "".join(f"padding_{i} = {i}\n" for i in range(45))
cases.extend([
    {"id": "long-direct", "origin": "curated synthetic",
     "source": "import math\n" + padding + "eval(input())\n",
     "expected": [{"line": 47, "severity": "S1", "triggered": True}]},
    {"id": "long-clean", "origin": "curated synthetic",
     "source": "import math\n" + padding + "print(math.pi)\n", "expected": []},
    {"id": "long-cross-function", "origin": "curated synthetic",
     "source": "def run(code):\n    eval(code)\n" + padding + "run(input())\n",
     "expected": [{"line": 2, "severity": "S1", "triggered": True}]},
    {"id": "long-unreachable", "origin": "curated synthetic",
     "source": "if False:\n    eval(input())\n" + padding,
     "expected": []},
])
(directory / "ablation_cases.json").write_text(
    json.dumps(cases, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(f"Wrote {len(cases)} synthetic cases")
