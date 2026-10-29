"""Run each predeclared scenario once with the established local preset."""
import json
from pathlib import Path
import benchmark

root = Path(__file__).resolve().parent
specs = json.loads((root / "scenarios/cases.json").read_text(encoding="utf-8"))
for folder in ["outputs", "logs", "results"]:
    (root / folder).mkdir(exist_ok=True)
executable = next((root / "runtime").rglob("sd-cli.exe"))
for case in specs["cases"]:
    preset = {"name": "scenario-" + case["id"], "size": 1024, "steps": 25,
              "cfg": 1.0, "vae_tile_size": 512,
              "prompt_file": "scenarios/prompts/" + case["id"] + ".txt"}
    result = benchmark.execute(preset, executable, 1, 7.0)
    if result["status"] != "success":
        raise SystemExit(1)
