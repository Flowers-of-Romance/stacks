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


def embed_text(text: str) -> list[float]:
    """Embed a single text and return a 384-dim float list."""
    model = get_model()
    embedding = model.encode(text, normalize_embeddings=True)
    return embedding.tolist()


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed multiple texts in a batch."""
    model = get_model()
    embeddings = model.encode(texts, normalize_embeddings=True)
    return [e.tolist() for e in embeddings]
