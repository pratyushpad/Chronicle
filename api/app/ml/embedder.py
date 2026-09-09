"""ONNX MiniLM sentence embedder — no torch, fits free-tier memory.

Lazy singleton: neither onnxruntime nor the model file is touched until the
first encode() call, so importing this module (or the API process serving
only keyword traffic) stays lightweight.

Releasable, too: see release_embedder(). On the 512 MB box the model is a
resident ~150-250 MB once loaded, which is the difference between serving
ordinary traffic comfortably and OOM'ing while idle.
"""
import gc
import logging
import threading

import numpy as np

log = logging.getLogger(__name__)

EMBEDDING_DIM = 384
MAX_TOKENS = 256
# Small batch keeps peak memory low so ingest embedding fits Render's 512MB free tier
# (larger batches OOM'd the box mid-ingest). Slower, but memory-safe.
DEFAULT_BATCH_SIZE = 16

# Guards _instance for BOTH get and release. FastAPI runs sync endpoints in a
# threadpool, so a semantic-search request can call get_embedder() at the same
# moment the ingest task calls release_embedder(); holding one coarse lock across
# each whole operation is what makes "load then hand out" and "drop" atomic with
# respect to each other. Contention is a non-issue — the only slow path under the
# lock is the one-time model load.
_lock = threading.Lock()
_instance: "Embedder | None" = None
# Encodes currently in flight (guarded by _lock). release_embedder() declines while
# this is non-zero: dropping the global mid-encode wouldn't break the running encode
# (it holds its own reference) but WOULD let the next get_embedder() load a second
# model while the first is still resident — two ~200 MB models on a 512 MB box is
# the OOM this module exists to prevent. The skipped release costs nothing: the next
# run's release (or the next idle one) picks it up.
_active_encodes = 0


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
        global _active_encodes
        with _lock:
            _active_encodes += 1
        try:
            return self._encode_batches(texts, batch_size)
        finally:
            with _lock:
                _active_encodes -= 1

    def _encode_batches(self, texts: list[str], batch_size: int) -> list[list[float]]:
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
    """Return the process-wide embedder, loading it on first use.

    Deliberately NOT double-checked locking: release_embedder() can null the global
    concurrently, and the unlocked fast-path read is exactly the window where a caller
    could observe a half-published or already-released instance. The whole check-load-
    return sequence runs under _lock instead.

    Callers must not hold a DB connection across this call — model load takes seconds
    on 0.1 vCPU and an idle in-transaction connection gets dropped by Neon (3d02be3).
    """
    global _instance
    with _lock:
        if _instance is None:
            _instance = Embedder()
        return _instance


def release_embedder() -> bool:
    """Drop the loaded model so its ~150-250 MB of RSS goes back to the OS.

    Safe to call when nothing is loaded — that's a no-op returning False. Returns True
    if an instance was actually dropped. Takes the same lock as get_embedder(), so a
    release can never interleave with an in-progress load (which would either tear down
    a half-built instance or leave two models resident at once).

    Only the module-global reference is dropped: a thread already inside encode() holds
    its own reference and finishes normally against the model it has. Ripping the ORT
    session out from under it would be a crash, not a saving — its memory comes back
    when that call returns and the object becomes garbage.
    """
    global _instance
    with _lock:
        if _instance is None:
            return False
        if _active_encodes > 0:
            # An encode is in flight (threadpool search, or a concurrent embed). Dropping
            # the global now would let the next get_embedder() load a SECOND model while
            # this one is still pinned by the running encode — transient double residency
            # is the one state a 512 MB box cannot absorb. Decline; a later release gets it.
            log.info("embedder busy (%d encode(s) in flight) — release skipped", _active_encodes)
            return False
        _instance = None
        # Explicit collect: ORT holds the arena through reference cycles, so without
        # this the RSS drop is deferred to whenever gen-2 next runs — which on an idle
        # web process can be a long time, i.e. exactly the window we're trying to fix.
        gc.collect()
    log.info("released ONNX embedder; next encode pays the reload")
    return True
