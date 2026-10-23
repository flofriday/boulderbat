"""One isolated CPU model run. Invoked by forecast_benchmark.run_timestral."""

import argparse
import importlib.metadata
import json
from pathlib import Path
import platform
import resource
import time


def main():
    parser = argparse.ArgumentParser()
    for name in ("inputs", "output", "model", "revision", "cache"):
        parser.add_argument(f"--{name}", required=True)
    parser.add_argument("--threads", type=int, required=True)
    args = parser.parse_args()

    import numpy as np
    import torch
    from huggingface_hub import snapshot_download
    from timestral import TimestralForecaster

    torch.set_num_threads(args.threads)
    torch.set_num_interop_threads(1)
    torch.manual_seed(42)
    torch.use_deterministic_algorithms(True)
    start = time.perf_counter()
    snapshot = Path(snapshot_download(args.model, revision=args.revision, cache_dir=args.cache,
                                     allow_patterns=["config.json", "model.safetensors"]))
    download_seconds = time.perf_counter() - start
    artifact_mb = sum((snapshot / name).stat().st_size for name in ("config.json", "model.safetensors")) / 1e6
    start = time.perf_counter()
    forecaster = TimestralForecaster.from_pretrained(str(snapshot), device="cpu")
    load_seconds = time.perf_counter() - start
    with np.load(args.inputs) as data:
        contexts = [data[f"context_{i}"] for i in range(len(data.files))]
    results, timings = [], []
    with torch.inference_mode():
        # Warm-up excluded from timings; identical case/order for every size.
        forecaster.forecast(contexts[0][None, None, :], prediction_length=64)
        for i, context in enumerate(contexts):
            start = time.perf_counter()
            forecast = forecaster.forecast(context[None, None, :], prediction_length=64)
            values = np.stack([np.asarray(forecast.quantile(q))[0, 0] for q in (.1, .5, .9)], axis=-1)
            timings.append((time.perf_counter() - start) * 1000)
            results.append(values)
            if i % 50 == 0:
                print(f"{args.model}: {i + 1}/{len(contexts)}", flush=True)
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    peak_mb = peak / (1e6 if platform.system() == "Darwin" else 1e6 / 1024)
    stats = {"status": "ok", "model_revision": args.revision, "device": "cpu",
             "dtype": "float32", "threads": args.threads, "batch_size": 1,
             "download_seconds": download_seconds, "load_seconds": load_seconds,
             "artifact_mb": artifact_mb, "peak_process_ram_mb": peak_mb,
             "median_inference_ms": float(np.median(timings)),
             "p95_inference_ms": float(np.quantile(timings, .95)),
             "inference_ms": timings,
             "versions": {name: importlib.metadata.version(name) for name in
                          ("timestral", "torch", "numpy", "huggingface-hub")}}
    output = Path(args.output)
    # Write predictions last: their existence plus runtime marks a completed run.
    (output / "runtime.json").write_text(json.dumps(stats, indent=2) + "\n")
    np.save(output / "predictions.npy", np.stack(results))


if __name__ == "__main__":
    main()
