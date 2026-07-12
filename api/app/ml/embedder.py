"""ONNX MiniLM sentence embedder — no torch, fits free-tier memory.

Lazy singleton: neither onnxruntime nor the model file is touched until the
first encode() call, so importing this module (or the API process serving
only keyword traffic) stays lightweight.
"""
import logging
import threading

import numpy as np

log = logging.getLogger(__name__)

EMBEDDING_DIM = 384
MAX_TOKENS = 256
# Small batch keeps peak memory low so ingest embedding fits Render's 512MB free tier
# (larger batches OOM'd the box mid-ingest). Slower, but memory-safe.
DEFAULT_BATCH_SIZE = 16

_lock = threading.Lock()
_instance: "Embedder | None" = None


def mean_pool(token_embeddings: np.ndarray, attention_mask: np.ndarray) -> np.ndarray:
    """Attention-masked mean pooling. (batch, seq, dim) + (batch, seq) -> (batch, dim)."""
    mask = attention_mask[..., None].astype(np.float32)
    summed = (token_embeddings * mask).sum(axis=1)
    counts = np.clip(mask.sum(axis=1), 1e-9, None)
    return summed / counts


def l2_normalize(vectors: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    return vectors / np.clip(norms, 1e-12, None)


class Embedder:
    def __init__(self) -> None:
        import onnxruntime as ort
        from tokenizers import Tokenizer

        from app.ml.download import model_dir

        directory = model_dir()
        model_path = directory / "model_quantized.onnx"
        tokenizer_path = directory / "tokenizer.json"
        if not model_path.exists() or not tokenizer_path.exists():
            raise FileNotFoundError(
                f"Embedding model not found in {directory} — run `python -m app.ml.download`"
            )
        self._tokenizer = Tokenizer.from_file(str(tokenizer_path))
        self._tokenizer.enable_truncation(max_length=MAX_TOKENS)
        self._tokenizer.enable_padding()
        self._session = ort.InferenceSession(
            str(model_path), providers=["CPUExecutionProvider"]
        )
        log.info("loaded ONNX MiniLM from %s", directory)

    def encode(self, texts: list[str], batch_size: int = DEFAULT_BATCH_SIZE) -> list[list[float]]:
        """Encode texts to L2-normalized 384-dim vectors."""
        out: list[list[float]] = []
        for start in range(0, len(texts), batch_size):
            batch = texts[start : start + batch_size]
            encodings = self._tokenizer.encode_batch(batch)
            input_ids = np.array([e.ids for e in encodings], dtype=np.int64)
            attention_mask = np.array([e.attention_mask for e in encodings], dtype=np.int64)
            token_type_ids = np.zeros_like(input_ids)
            (token_embeddings,) = self._session.run(
                None,
                {
                    "input_ids": input_ids,
                    "attention_mask": attention_mask,
                    "token_type_ids": token_type_ids,
                },
            )[:1]
            pooled = mean_pool(token_embeddings, attention_mask)
            out.extend(l2_normalize(pooled).astype(np.float32).tolist())
        return out


def get_embedder() -> Embedder:
    global _instance
    if _instance is None:
        with _lock:
            if _instance is None:
                _instance = Embedder()
    return _instance
