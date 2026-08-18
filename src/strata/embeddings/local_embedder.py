"""Local embedding generation via sentence-transformers.

Loads the model once at module level (lazy, on first call) to avoid
repeated initialization overhead.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from strata.config import get_settings

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer

# Lazy-loaded singleton — avoids importing torch at module load time,
# which is slow and unneeded if embeddings aren't used in that run.
_model: SentenceTransformer | None = None


def _get_model() -> SentenceTransformer:
    """Load the sentence-transformers model (once)."""
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer

        settings = get_settings()
        _model = SentenceTransformer(settings.embedding_model_name)
    return _model


def embed(text: str) -> list[float]:
    """Embed a single text string into a 384-dim float vector."""
    model = _get_model()
    vector = model.encode(text, normalize_embeddings=True)
    return vector.tolist()


def embed_batch(texts: list[str]) -> list[list[float]]:
    """Embed a batch of text strings.

    More efficient than calling embed() in a loop because
    sentence-transformers batches the forward pass.
    """
    if not texts:
        return []
    model = _get_model()
    vectors = model.encode(texts, normalize_embeddings=True, batch_size=64)
    return [v.tolist() for v in vectors]
