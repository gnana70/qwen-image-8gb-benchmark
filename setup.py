"""Download verified public weights and an isolated Windows CUDA runtime."""
import concurrent.futures
import hashlib
import json
import shutil
import time
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
HEADERS = {"User-Agent": "QwenLocalBenchmark/1.0"}


def open_url(url, headers=None):
    return urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS | (headers or {})), timeout=60)


def get_json(url):
    for attempt in range(8):
        try:
            with open_url(url) as response:
                return json.load(response)
        except Exception as error:
            print(f"Metadata retry {attempt+1}: {type(error).__name__}", flush=True)
            if attempt == 7:
                raise
            time.sleep(2)


def download(item):
    path = ROOT / item["path"]
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(path.suffix + ".part")
    if not path.exists():
        for attempt in range(12):
            try:
                offset = partial.stat().st_size if partial.exists() else 0
                headers = {"Range": f"bytes={offset}-"} if offset else {}
                with open_url(item["url"], headers) as response:
                    mode = "ab" if offset and response.status == 206 else "wb"
                    if mode == "wb":
                        offset = 0
                    started = last = time.monotonic()
                    count = offset
                    with partial.open(mode) as output:
                        while chunk := response.read(4 * 1024 * 1024):
                            output.write(chunk)
                            count += len(chunk)
                            now = time.monotonic()
                            if now - last >= 20:
                                print(f"{path.name}: {count/1e9:.2f}/{item['size']/1e9:.2f} GB, {(count-offset)/max(now-started,1)/1e6:.1f} MB/s", flush=True)
                                last = now
                if partial.stat().st_size != item["size"]:
                    raise ValueError("Incomplete download")
                partial.replace(path)
                break
            except Exception as error:
                print(f"{path.name} retry {attempt+1}: {type(error).__name__}: {error}", flush=True)
                if attempt == 11:
                    raise
                time.sleep(2)
    if path.stat().st_size != item["size"]:
        raise ValueError(f"Size mismatch: {path}")
    if item.get("sha256"):
        digest = hashlib.file_digest(path.open("rb"), "sha256").hexdigest()
        if digest != item["sha256"]:
            raise ValueError(f"SHA256 mismatch: {path}")
    print(f"Verified {path.name}", flush=True)


def main():
    started = time.monotonic()
    models = [
        ("abenzerps/Qwen-Image-2.1-Uncensored-Quantized", "qwen-image-2.1-UC-Q4_K_M.gguf"),
        ("abenzerps/Qwen-Image-2.1-Uncensored-Quantized", "vae/qwen_image_2.1_vae_bf16.safetensors"),
        ("Qwen/Qwen3-VL-8B-Instruct-GGUF", "Qwen3VL-8B-Instruct-Q4_K_M.gguf"),
    ]
    metadata = {}
    items = []
    for repo, filename in models:
        if repo not in metadata:
            metadata[repo] = get_json(f"https://huggingface.co/api/models/{repo}?blobs=true")
        model = metadata[repo]
        match = next((x for x in model["siblings"] if x["rfilename"] == filename), None)
        if match is None:
            raise ValueError(f"Missing {filename}; candidates: {[x['rfilename'] for x in model['siblings'] if 'Q4_K_M' in x['rfilename']]}")
        items.append({"repo": repo, "revision": model["sha"], "filename": filename,
                      "path": "models/" + Path(filename).name,
                      "url": f"https://huggingface.co/{repo}/resolve/{model['sha']}/{filename}?download=true",
                      "size": match["size"], "sha256": match["lfs"]["sha256"]})
    release = get_json("https://api.github.com/repos/leejet/stable-diffusion.cpp/releases/latest")
    for name in ["cudart-sd-bin-win-cu12-x64.zip", next(x["name"] for x in release["assets"] if "bin-win-cuda12-x64.zip" in x["name"])]:
        asset = next(x for x in release["assets"] if x["name"] == name)
        items.append({"path": "downloads/" + name, "url": asset["browser_download_url"],
                      "size": asset["size"], "sha256": (asset.get("digest") or "").removeprefix("sha256:")})
    manifest = {"runtime_release": release["tag_name"], "files": items}
    (ROOT / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    total = sum(x["size"] for x in items)
    free = shutil.disk_usage(ROOT).free
    print(f"Downloads: {total/1e9:.2f} GB; free disk: {free/1e9:.2f} GB", flush=True)
    if free < total + 3_000_000_000:
        raise RuntimeError("Insufficient free disk space")
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(download, items))
    destination = ROOT / "runtime"
    destination.mkdir(exist_ok=True)
    for item in items:
        if item["path"].endswith(".zip"):
            with zipfile.ZipFile(ROOT / item["path"]) as archive:
                for member in archive.infolist():
                    target = (destination / member.filename).resolve()
                    if not target.is_relative_to(destination.resolve()):
                        raise ValueError("Unsafe archive member")
                archive.extractall(destination)
    manifest["setup_elapsed_seconds"] = time.monotonic() - started
    (ROOT / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Setup complete in {manifest['setup_elapsed_seconds']:.1f}s", flush=True)


if __name__ == "__main__":
    main()
