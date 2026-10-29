"""Render predeclared scenario pairs and transparent manual review notes."""
import hashlib
import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def build_section():
    directory = ROOT / "scenarios"
    required = [directory / p for p in ["cases.json", "cloud-timings.json", "reviews.json"]]
    if not all(p.exists() for p in required):
        return ""
    specs = json.loads(required[0].read_text(encoding="utf-8"))
    cloud_data = json.loads(required[1].read_text(encoding="utf-8-sig"))
    reviews = json.loads(required[2].read_text(encoding="utf-8"))
    cloud = {x["id"]: x for x in cloud_data["runs"]}
    summary, pairs, measurements = [], [], []
    escape = html.escape
    ordered_cases = sorted(specs["cases"], key=lambda c: 0 if c.get("category") == "Non-explicit romance and fashion" else 1)
    for case in ordered_cases:
        ident = case["id"]
        local_file = ROOT / f"results/scenario-{ident}.json"
        if ident not in cloud or not local_file.exists():
            continue
        local = json.loads(local_file.read_text())
        if local["status"] != "success":
            continue
        reference = cloud[ident]
        prompt = (ROOT / f"scenarios/prompts/{ident}.txt").read_text(encoding="utf-8").strip()
        digest = hashlib.sha256(prompt.encode()).hexdigest()
        assert digest == local["prompt_sha256"] == reference["prompt_sha256"]
        review = reviews["cases"][ident]
        vram = local["peak_device_vram_mib"] / 1024
        ram = local["peak_process_working_set_bytes"] / 2**30
        cloud_time, local_time = reference["elapsed_seconds"], local["elapsed_seconds"]
        summary.append(f'<tr><th><a href="#scenario-{ident}">{escape(case["title"])}</a></th><td>{cloud_time:.1f} s</td><td>{local_time:.1f} s</td><td>{vram:.2f} GiB</td><td>{escape(review["summary"])}</td></tr>')
        cards = []
        for engine, label, source, elapsed, dims in [
            ("cloud", "Built-in ImageGen / cloud", reference["image_file"], cloud_time, reference["actual_dimensions"]),
            ("qwen", "Local Qwen / Q4_K_M", f"outputs/scenario-{ident}.png", local_time, local["actual_dimensions"]),
        ]:
            assert (ROOT / source).is_file()
            notes = review[engine]
            cards.append(f'<article><header><h2>{label}</h2><p>{elapsed:.1f} s · {dims[0]} × {dims[1]}</p></header><a href="{source}"><img src="{source}" alt="{escape(case["title"])} — {label}" loading="lazy"></a><p class="note"><strong>Prompt checks:</strong> {escape(notes["observation"])}</p><p class="note"><strong>Visual quality:</strong> {escape(notes["quality"])}</p></article>')
        check_rows = []
        for index, criterion in enumerate(case["checks"]):
            values = []
            for engine in ["cloud", "qwen"]:
                status = review[engine]["checks"][index]
                values.append(f'<td><span class="status {status}">{status.title()}</span></td>')
            check_rows.append(f'<tr><td>{escape(criterion)}</td>{"".join(values)}</tr>')
        pairs.append(f'<section id="scenario-{ident}" class="scenario"><h2 class="scenario-title">{escape(case["title"])}</h2><p>{escape(review["summary"])}</p><div class="gallery">{"".join(cards)}</div><div class="table-wrap"><table><thead><tr><th>Predeclared check</th><th>Cloud</th><th>Qwen</th></tr></thead><tbody>{"".join(check_rows)}</tbody></table></div><details><summary>Exact shared prompt · {ident}</summary><pre>{escape(prompt)}</pre><p><a href="scenarios/prompts/{ident}.txt">Open prompt file</a></p></details></section>')
        measurements.append({"id": ident, "title": case["title"], "cloud_seconds": cloud_time,
                             "local_seconds": local_time, "local_peak_device_vram_gib": vram,
                             "local_peak_process_ram_gib": ram, "cloud_dimensions": reference["actual_dimensions"],
                             "local_dimensions": local["actual_dimensions"], "prompt_sha256": digest,
                             "manual_review": review})
    (directory / "summary.json").write_text(json.dumps(measurements, indent=2), encoding="utf-8")
    section = f'<section id="scenarios"><div class="eyebrow">Scenario tests · First sample only · 27 October 2026</div><h1>{len(measurements)} scenarios.<br>One attempt each.</h1>'
    section += f'<p>One cloud image and one local Qwen image for each scenario, using the exact same prompt. All {len(measurements)} local runs succeeded at <strong>1024 × 1024, 25 steps, CFG 1, seed 42, 512-pixel decoding tiles</strong>, with a 7 GiB managed GPU budget. No rerolls, manual prompt changes or selected best samples.</p>'
    if any(c.get("category") == "Non-explicit romance and fashion" for c in ordered_cases):
        section += '<p><strong>Latest addition:</strong> three fully clothed, non-explicit romance and fashion scenes, shown first. Both engines generated an image for all three prompts; no refusal was observed in these cases. This does not establish an uncensored-content claim or behavior beyond the tested prompts.</p>'
    section += '<div class="table-wrap scenario-summary"><table><thead><tr><th>Scenario</th><th>Cloud round trip</th><th>Qwen total</th><th>Qwen peak VRAM</th><th>Observed result</th></tr></thead><tbody>' + ''.join(summary) + '</tbody></table></div>'
    section += '<p class="muted">Local times include loading, text encoding, sampling, decoding and saving; filesystem caches may be warm. Cloud times include service processing and transfer; its hardware, version and sampler are not exposed. Cloud outputs returned 1254 × 1254 pixels, while local outputs are 1024 × 1024. Cloud generation ran remotely while the local cases ran sequentially. These are manual first-sample checks, not official GenEval, FID, OCR or model-wide ranking scores. Pass means the listed criterion looks satisfied in this image; partial indicates a visible minor shortfall or uncertainty.</p>'
    section += '<p>The linked <a href="https://github.com/ziqihuangg/Awesome-Evaluation-of-Visual-Generation">evaluation resource catalogue</a> distinguishes quality and input consistency. The object-count, colour and position checks here are inspired by <a href="https://github.com/djghosh13/geneval">GenEval</a>; these custom scenes are not its official test set. Portrait microtexture, hand/material realism and affectionate interaction are recorded separately as visual observations.</p>'
    return section + ''.join(pairs) + '</section><hr class="section-break">'
