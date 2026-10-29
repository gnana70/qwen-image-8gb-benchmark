"""Build a self-contained comparison page using local original image files."""
import html
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent


def main():
    reference = json.loads((ROOT / "reference-timing.json").read_text())
    hardware = json.loads((ROOT / "hardware.json").read_text())
    reviews = json.loads((ROOT / "quality-reviews.json").read_text()) if (ROOT / "quality-reviews.json").exists() else {}
    order = ["draft-512-10", "balanced-768-20", "detail-1024-25", "quality-1024-40", "guidance-1024-25-cfg6", "decode-1024-25-tile512", "detail-1024-25-repeat2"]
    labels = dict(zip(order, ["Draft", "Balanced", "Detail — first run", "More steps", "Higher guidance", "Larger decoding tiles", "Detail — repeat"]))
    rows, cards, summary = [], [], []
    for name in order:
        path = ROOT / "results" / (name + ".json")
        if not path.exists():
            continue
        result = json.loads(path.read_text())
        if result["status"] != "success":
            continue
        total = result["elapsed_seconds"]
        vram = result.get("peak_device_vram_mib", 0) / 1024
        ram = result.get("peak_process_working_set_bytes", 0) / 2**30
        sampling = next((float(match.group(1)) for line in result["reported_timing_lines"] if (match := re.search(r"sampling completed, taking ([\d.]+)s", line))), None)
        note = reviews.get(name, {}).get("observation", "")
        label = html.escape(labels[name])
        if result.get("vae_tile_size"):
            note += f" Requested decoding tile: {result['vae_tile_size']} pixels; inspect native log for automatic fallback."
        rows.append(f'<tr><th><a href="outputs/{name}.png">{label}</a></th><td>{result["size"]}²</td><td>{result["steps"]}</td><td>{result["cfg"]:g}</td><td>{total:.1f} s</td><td>{sampling:.2f} s</td><td>{vram:.2f} GiB</td><td>{ram:.2f} GiB</td></tr>')
        card = f'<article><header><h2>{label}</h2><p>{result["size"]} × {result["size"]} · {result["steps"]} steps · CFG {result["cfg"]:g}<br>{total:.1f} s total · {vram:.2f} GiB peak VRAM</p></header><a href="outputs/{name}.png"><img src="outputs/{name}.png" alt="{label}" loading="lazy"></a><p class="note">{html.escape(note)}</p></article>'
        if name == "decode-1024-25-tile512":
            cards.insert(0, card)
        else:
            cards.append(card)
        summary.append({"preset": name, "total_seconds": round(total, 3), "sampling_phase_seconds": sampling, "peak_vram_gib": round(vram, 3), "peak_process_ram_gib": round(ram, 3), "observation": note})
    prompt = html.escape((ROOT / "prompt.txt").read_text())
    page = '''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Qwen Image 2.1 — measured comparison</title><style>
*{box-sizing:border-box}body{margin:0;background:#f5f3ed;color:#202522;font:16px/1.55 "Segoe UI",Arial,sans-serif}main{max-width:1450px;margin:auto;padding:45px 28px}h1{font-size:clamp(32px,4vw,58px);line-height:1.1;letter-spacing:-1.8px;margin:8px 0 20px}h2{font-size:19px;margin:0}p{max-width:1000px}a{color:#19573c}.eyebrow{font-size:12px;letter-spacing:2px;text-transform:uppercase}.muted{color:#58615b}.table-wrap{overflow:auto;margin:28px 0 40px}table{border-collapse:collapse;width:100%;white-space:nowrap;background:#fff}th,td{text-align:left;padding:13px 15px;border-bottom:1px solid #dce0d7}thead{font-size:12px;text-transform:uppercase;letter-spacing:.4px}tbody th{font-weight:500}.gallery{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:26px}article{background:#fff;border:1px solid #dce0d7;overflow:hidden}article header{padding:18px 20px}article header p{margin:5px 0 0;color:#58615b;font-size:14px}img{display:block;width:100%;aspect-ratio:1;object-fit:contain;background:#e9e8e2}.note{padding:0 20px 8px;font-size:15px}details{margin:30px 0;border-top:1px solid #cdd3ca;padding-top:18px}summary{cursor:pointer;font-weight:600}pre{white-space:pre-wrap;font:14px/1.6 "Segoe UI",Arial,sans-serif;background:#fff;padding:22px}footer{margin-top:35px;font-size:14px;color:#58615b}@media(max-width:760px){main{padding:24px 14px}.gallery{grid-template-columns:1fr}th,td{padding:10px}}
</style><main><div class="eyebrow">27 October 2026 · One prompt · Original outputs</div><h1>Qwen Image 2.1<br>Local vs. cloud reference</h1>'''
    page += f'<p><strong>{html.escape(hardware["gpu"])}</strong> · 32 GB installed RAM. Local diffusion and text encoder both use Q4_K_M weights. Seed 42, Euler/simple, automatic memory placement and attention, 7 GiB managed GPU budget, tiled VAE (256-pixel default; one 512-pixel tile test).</p>'
    page += '<p><strong>Best observed local starting point:</strong> 1024 × 1024, 25 steps, CFG 1, 512-pixel decoding tiles. This run took <strong>114.3 seconds</strong> and peaked at <strong>6.27 GiB VRAM</strong>, with three oranges and the correct sign. The default 25-step baseline took 183.3 seconds initially and 127.1 seconds on repeat; the repeated image was pixel-identical. These are observed runs, not statistically controlled averages.</p>'
    page += '<div class="table-wrap"><table><thead><tr><th>Run</th><th>Size</th><th>Steps</th><th>CFG</th><th>Total time</th><th>Sampling phase*</th><th>Peak device VRAM</th><th>Peak process RAM</th></tr></thead><tbody>'
    page += f'<tr><th>Built-in ImageGen / cloud</th><td>1254²</td><td>Hidden</td><td>Hidden</td><td>{reference["elapsed_seconds"]:.1f} s</td><td>—</td><td>—</td><td>—</td></tr>' + ''.join(rows) + '</tbody></table></div>'
    page += '<p class="muted">Cloud time is the observed tool round trip. Local total time includes loading, prompt encoding, sampling, decoding, saving and process cleanup. *The native sampling phase includes lazy diffusion-weight loading; it is not pure denoising time. Downloads and installation are excluded. One run per setting, with a second 1024/25 baseline to investigate loading variation; OS cache, background apps and thermal state can affect timing. The cloud model version, hardware, seed and sampler are not exposed, and its returned resolution differs.</p>'
    page += f'<div class="gallery"><article><header><h2>Cloud reference — built-in ImageGen</h2><p>{reference["elapsed_seconds"]:.1f} s tool round trip · 1254 × 1254</p></header><a href="reference-imagegen.png"><img src="reference-imagegen.png" alt="Cloud reference"></a><p class="note">Three oranges, full face, correct sign wording and two-line layout, clear pouring action.</p></article>' + ''.join(cards) + '</div>'
    page += f'<details><summary>Exact shared prompt</summary><pre>{prompt}</pre></details><details><summary>Reproduce and inspect the measurements</summary><p>Use run.ps1 to repeat the presets. The results folder stores the exact commands and measured data; logs stores native output and per-second GPU telemetry. Model revisions and SHA256 checksums are in manifest.json. README.md explains the test matrix and measurement limits. Original PNGs are linked above; click an image to inspect it at its native resolution.</p></details><footer>Sources: <a href="https://huggingface.co/abenzerps/Qwen-Image-2.1-Uncensored-Quantized">Requested model</a> · <a href="https://github.com/leejet/stable-diffusion.cpp/blob/master/docs/qwen_image_2.1.md">Runtime documentation</a>. This single benign prompt tests scene rendering and instruction following, not broad model quality.</footer></main></html>'
    from scenario_report import build_section
    scenarios = build_section()
    if scenarios:
        extra_css = '<style>nav{display:flex;gap:24px;margin:0 0 36px;padding-bottom:16px;border-bottom:1px solid #cdd3ca}.scenario{margin-top:48px;scroll-margin-top:20px}.scenario-title{font-size:28px;letter-spacing:-.6px}.status{font-weight:600}.pass{color:#19573c}.partial{color:#8a5b12}.fail{color:#a33525}.section-break{border:0;border-top:2px solid #cdd3ca;margin:60px 0}.scenario-summary table{white-space:normal}.scenario-summary th:first-child{min-width:210px}.scenario-summary td:last-child{min-width:300px}.scenario .table-wrap table{white-space:normal}</style>'
        navigation = '<nav><a href="#scenarios">New scenario tests</a><a href="#settings">Original settings benchmark</a></nav>'
        page = page.replace('<main>', extra_css + '<main>' + navigation + scenarios + '<section id="settings">', 1)
        page = page.replace('</main></html>', '</section></main></html>')
        page = page.replace('27 October 2026 · One prompt · Original outputs', 'Original settings benchmark · 27 October 2026 · One prompt')
    (ROOT / "comparison.html").write_text(page, encoding="utf-8")
    (ROOT / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print("Saved comparison.html and summary.json")


if __name__ == "__main__":
    main()
