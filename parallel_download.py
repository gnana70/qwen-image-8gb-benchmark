"""Resume model files with eight checked HTTP range transfers."""
import concurrent.futures
import hashlib
import json
import threading
import time
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LOCK = threading.Lock()
STATE_PATH = ROOT / "download-state.json"


def main():
    manifest = json.loads((ROOT / "manifest.json").read_text())
    items = manifest["files"]
    state = json.loads(STATE_PATH.read_text()) if STATE_PATH.exists() else {}
    jobs_by_file = []
    for item in items:
        path = ROOT / item["path"]
        if path.exists() and path.stat().st_size == item["size"]:
            continue
        part = path.with_suffix(path.suffix + ".part")
        if path.exists() and not part.exists():
            path.replace(part)
        if item["path"] not in state:
            prefix = part.stat().st_size if part.exists() else 0
            state[item["path"]] = {"prefix": prefix, "done": []}
        entry = state[item["path"]]
        jobs = []
        for start in range(entry["prefix"], item["size"], 64 * 1024 * 1024):
            end = min(start + 64 * 1024 * 1024, item["size"]) - 1
            if start not in entry["done"]:
                jobs.append((item, start, end))
        jobs_by_file.append(jobs)
        print(f"{path.name}: retained {entry['prefix']/1e9:.2f} GB; {len(jobs)} ranges remaining", flush=True)
    STATE_PATH.write_text(json.dumps(state), encoding="utf-8")

    def transfer(job):
        item, start, end = job
        part = (ROOT / item["path"]).with_suffix(Path(item["path"]).suffix + ".part")
        cursor = start
        for attempt in range(16):
            try:
                request = urllib.request.Request(item["url"], headers={"Range": f"bytes={cursor}-{end}", "User-Agent": "QwenBenchmark/1.0"})
                with urllib.request.urlopen(request, timeout=45) as response:
                    expected = f"bytes {cursor}-{end}/{item['size']}"
                    if response.status != 206 or response.headers.get("Content-Range") != expected:
                        raise ValueError(f"Unexpected range response {response.status}: {response.headers.get('Content-Range')}")
                    remaining = end - cursor + 1
                    with part.open("r+b" if part.exists() else "w+b") as output:
                        output.seek(cursor)
                        while remaining:
                            chunk = response.read(min(1024 * 1024, remaining))
                            if not chunk:
                                raise EOFError("Incomplete range")
                            output.write(chunk)
                            cursor += len(chunk)
                            remaining -= len(chunk)
                with LOCK:
                    state[item["path"]]["done"].append(start)
                    STATE_PATH.write_text(json.dumps(state), encoding="utf-8")
                return end-start+1
            except Exception as error:
                if attempt in (0, 7, 15):
                    print(f"Range retry {attempt+1} {Path(item['path']).name} offset {cursor}: {type(error).__name__}: {error}", flush=True)
                if attempt == 15:
                    raise
                time.sleep(1)

    jobs = []
    for index in range(max(map(len, jobs_by_file), default=0)):
        for file_jobs in jobs_by_file:
            if index < len(file_jobs):
                jobs.append(file_jobs[index])
    started = last = time.monotonic()
    complete = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
        for future in concurrent.futures.as_completed([pool.submit(transfer, job) for job in jobs]):
            complete += future.result()
            now = time.monotonic()
            if now-last > 15:
                print(f"Range transfers: {complete/1e9:.2f} GB complete, {complete/(now-started)/1e6:.1f} MB/s aggregate", flush=True)
                last = now
    for item in items:
        path = ROOT / item["path"]
        part = path.with_suffix(path.suffix + ".part")
        target = path if path.exists() else part
        with target.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        if digest != item["sha256"] or target.stat().st_size != item["size"]:
            raise ValueError(f"Verification failed: {target}")
        if target != path:
            part.replace(path)
        print(f"SHA256 verified: {path.name}", flush=True)
    print("All models verified", flush=True)
    destination = ROOT / "runtime"
    destination.mkdir(exist_ok=True)
    for item in items:
        if item["path"].endswith(".zip"):
            with zipfile.ZipFile(ROOT / item["path"]) as archive:
                for member in archive.infolist():
                    if not (destination / member.filename).resolve().is_relative_to(destination.resolve()):
                        raise ValueError("Unsafe archive member")
                archive.extractall(destination)
    manifest["parallel_download_elapsed_seconds"] = time.monotonic()-started
    (ROOT / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print("CUDA runtime extracted", flush=True)


if __name__ == "__main__":
    main()
