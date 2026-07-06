"""Fetch the quantized MiniLM ONNX model + tokenizer into MODEL_DIR.

Run at build time (Render build command / local setup):

    python -m app.ml.download

Idempotent — skips files that already exist. The int8-quantized
all-MiniLM-L6-v2 is ~23 MB and needs no torch at runtime.
"""
import logging
import os
import shutil
from pathlib import Path

from huggingface_hub import hf_hub_download

log = logging.getLogger(__name__)

HF_REPO = "Xenova/all-MiniLM-L6-v2"
MODEL_FILE = "onnx/model_quantized.onnx"
TOKENIZER_FILE = "tokenizer.json"

DEFAULT_MODEL_DIR = Path(__file__).resolve().parents[2] / "models" / "minilm"


def model_dir() -> Path:
    return Path(os.getenv("MODEL_DIR", str(DEFAULT_MODEL_DIR)))


def ensure_model(force: bool = False) -> Path:
    """Download model + tokenizer into model_dir(); return the dir."""
    target = model_dir()
    target.mkdir(parents=True, exist_ok=True)
    for repo_file, local_name in [(MODEL_FILE, "model_quantized.onnx"), (TOKENIZER_FILE, "tokenizer.json")]:
        dest = target / local_name
        if dest.exists() and not force:
            log.info("%s already present, skipping", dest)
            continue
        cached = hf_hub_download(repo_id=HF_REPO, filename=repo_file)
        shutil.copy(cached, dest)
        log.info("downloaded %s -> %s", repo_file, dest)
    return target


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(f"model ready in {ensure_model()}")
