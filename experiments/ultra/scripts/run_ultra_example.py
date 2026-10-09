"""Run the official CoDExSmall inference example on CPU, without training."""

import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = ROOT / "vendor" / "ULTRA"


def main():
    source = UPSTREAM / "config" / "transductive" / "inference.yaml"
    if not source.exists():
        raise SystemExit("Clone the official ULTRA repository into vendor/ULTRA first.")

    output = ROOT / "output" / "ultra-example"
    output.mkdir(parents=True, exist_ok=True)
    # Preserve the upstream model and evaluation settings; relocate its files.
    config = source.read_text().replace(
        "~/git/ULTRA/output", str(output)
    ).replace("~/git/ULTRA/kg-datasets/", str(ROOT / "data" / "benchmarks"))
    config_path = output / "inference.yaml"
    config_path.write_text(config)

    env = os.environ.copy()
    env["PATH"] = str(Path(sys.executable).parent) + os.pathsep + env.get("PATH", "")
    env["TORCH_EXTENSIONS_DIR"] = str(ROOT / ".cache" / "torch_extensions")
    env.setdefault("MAX_JOBS", "2")
    env.setdefault("OMP_NUM_THREADS", "1")
    env.setdefault("MKL_NUM_THREADS", "1")
    env["PYTHONUNBUFFERED"] = "1"
    command = [
        sys.executable, str(UPSTREAM / "script" / "run.py"),
        "-c", str(config_path),
        "--dataset", "CoDExSmall",
        "--epochs", "0", "--bpe", "null", "--gpus", "null",
        "--ckpt", str(UPSTREAM / "ckpts" / "ultra_4g.pth"),
    ]
    print("Running pretrained ULTRA on CoDExSmall (CPU; no training).", flush=True)
    print(f"Results: {output}", flush=True)
    subprocess.run(command, cwd=ROOT, env=env, check=True)


if __name__ == "__main__":
    main()
