"""Embedding generation using sentence-transformers."""
import os
import warnings
import logging

# Suppress all noisy warnings before importing anything
os.environ["TOKENIZERS_PARALLELISM"] = "false"
warnings.filterwarnings("ignore")
logging.getLogger("sentence_transformers").setLevel(logging.ERROR)
logging.getLogger("transformers").setLevel(logging.ERROR)
logging.getLogger("torch").setLevel(logging.ERROR)
logging.getLogger("safetensors").setLevel(logging.ERROR)

from sentence_transformers import SentenceTransformer

_model = None
MODEL_NAME = "intfloat/multilingual-e5-small"


def get_model() -> SentenceTransformer:
    """Get the embedding model (lazy singleton)."""
    global _model
    if _model is None:
        from huggingface_hub.utils import disable_progress_bars
        disable_progress_bars()
        _model = SentenceTransformer(MODEL_NAME)
    return _model


def _try_server(payload: dict) -> dict | None:
    """Try to get embedding from running server. Returns None if unavailable."""
    import urllib.request
    import json
    from stacks.server import DEFAULT_PORT

    try:
        data = json.dumps(payload).encode()
        req = urllib.request.Request(
            f"http://127.0.0.1:{DEFAULT_PORT}/embed",
            data=data,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read())
    except Exception:
        return None


def embed_text(text: str) -> list[float]:
    """Embed a single text and return a 384-dim float list.

    Uses the embedding server if running, otherwise loads model directly.
    """
    result = _try_server({"text": text})
    if result and "embedding" in result:
        return result["embedding"]

    model = get_model()
    embedding = model.encode(text, normalize_embeddings=True)
    return embedding.tolist()


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed multiple texts in a batch."""
    result = _try_server({"texts": texts})
    if result and "embeddings" in result:
        return result["embeddings"]

    model = get_model()
    embeddings = model.encode(texts, normalize_embeddings=True)
    return [e.tolist() for e in embeddings]
