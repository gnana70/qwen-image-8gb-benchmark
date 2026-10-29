# Qwen-Image 2.1 (Q4_K_M GGUF) on an 8 GB laptop GPU: benchmark scripts

Companion code for the Singularity Feed video **[Local AI vs. Cloud: Can Qwen-Image 2.1 Keep Up?](https://youtu.be/WL6Qm3tyGLg)**.

It downloads pinned, checksum-verified model files and an isolated stable-diffusion.cpp CUDA runtime, runs a settings
sweep and seven scenario prompts, and records wall time, native timing lines, nvidia-smi telemetry (1 s) and memory for
every run. Windows + NVIDIA GPU; Python 3.10+ standard library only.

## Quick start (PowerShell)
```powershell
python setup.py                      # model files (about 10.3 GB) + CUDA runtime, SHA256-checked
.\run.ps1 -Preset decode-1024-25-tile512   # one 1024 x 1024 image at the video's settings
python run_scenarios.py              # the 7 scored scenario prompts
python make_report.py; python scenario_report.py   # rebuild comparison.html and the summaries
```
If a large download stalls, `parallel_download.py` resumes the model files with eight checked range transfers.

## Files
| File | Purpose |
|---|---|
| `setup.py` | Downloads the files listed in `manifest.json` (Hugging Face revisions + SHA256) and the stable-diffusion.cpp CUDA 12 release, then extracts the runtime. |
| `parallel_download.py` | Resumes the model downloads with eight parallel, checked HTTP range transfers. |
| `manifest.json` | Exact sources, revisions, sizes and SHA256 of the 3 model files and 2 runtime archives. |
| `benchmark.py` | Runs one preset in a fresh process; writes `outputs/`, `logs/` (native log + GPU CSV) and `results/` JSON. |
| `run.ps1` | Runs the settings presets: `.\run.ps1` or `.\run.ps1 -Preset decode-1024-25-tile512 -Repeat 2`. |
| `run_scenarios.py` | Runs the 7 scenario prompts in `scenarios/cases.json` with the chosen preset. |
| `make_report.py`, `scenario_report.py` | Rebuild `comparison.html`, `summary.json` and `scenarios/summary.json` from saved results. |
| `prompt.txt` | The café warm-up prompt. |
| `scenarios/cases.json`, `scenarios/prompts/` | The scenario prompts and the checklists declared before generation. |
| `scenarios/reviews.json` | Manual pass / partial / fail per check for both engines (see the correction note below). |
| `results/`, `summary.json`, `hardware.json` | The measurements behind the video. |

## Model files (about 10.3 GB)
- `qwen-image-2.1-UC-Q4_K_M.gguf` (4.60 GB) from `abenzerps/Qwen-Image-2.1-Uncensored-Quantized`
- `Qwen3VL-8B-Instruct-Q4_K_M.gguf` (5.03 GB) from `Qwen/Qwen3-VL-8B-Instruct-GGUF`
- `qwen_image_2.1_vae_bf16.safetensors` (0.68 GB) from `abenzerps/Qwen-Image-2.1-Uncensored-Quantized`

## Settings used in the video
1024 × 1024, 25 steps, CFG 1, Euler, simple scheduler, seed 42, `--auto-fit on --max-vram 7.0`, `--vae-tiling --vae-tile-size 512`.
Note: stable-diffusion.cpp's own Qwen-Image 2.1 example uses `--cfg-scale 6.0`; CFG 1 roughly halves sampling time.

## Results (RTX 3070 Ti Laptop GPU, 8 GB)
- 72-77 s per 1024 × 1024 image with cached files; peak VRAM 6.3 GB; process RAM peak about 5.8 GB.
- 34 pre-declared checks over 7 prompts, one sample each: local 26 pass / 3 partial / 5 fail; cloud reference 33 pass / 1 partial.

**Correction:** the original manual review marked the local typography poster 4/4. Its last line actually reads
`BOOK AT NIGHTMARKETET.EXEIAMPLE`, so check 3 is a fail; `scenarios/reviews.json` here contains the corrected value.

## Notes
- The weights carry the Qwen Research License (commercial use needs a separate agreement). The model card states the
  build has no built-in safety checker or content filter; what you generate is your responsibility.
- Absolute paths in `results/*.json` were shortened to `<benchmark>` for publication.
- Model weights, runtime, downloads and generated images are not included (see `.gitignore`).
