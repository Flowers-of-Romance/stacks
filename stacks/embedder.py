"""Embedding generation using sentence-transformers."""
from sentence_transformers import SentenceTransformer

_model = None
MODEL_NAME = "intfloat/multilingual-e5-small"


def get_model() -> SentenceTransformer:
    """Get the embedding model (lazy singleton)."""
    global _model
    if _model is None:
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
