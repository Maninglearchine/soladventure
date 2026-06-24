from __future__ import annotations

import os

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from ai.finance_docs import FINANCE_DOCS, ZONE_TO_DOC_IDS

# Module-level embedding cache — {doc_id: list[float]}
# Survives across QuizGenerator re-instantiations within the same process.
_EMBED_CACHE: dict[str, list[float]] = {}


def _get_api_key() -> str | None:
    try:
        import streamlit as st
        key = st.session_state.get("openai_api_key")
        if key:
            return key
    except Exception:
        pass
    return os.environ.get("OPENAI_API_KEY")


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


class RAGEngine:
    def __init__(self):
        self.docs = FINANCE_DOCS
        self._use_embeddings = False

        # Try OpenAI embeddings first; fill cache for any docs not yet embedded.
        self._try_build_embeddings()

        # Always build TF-IDF so search() can fall back without error.
        self.vectorizer = TfidfVectorizer(
            analyzer="char_wb",
            ngram_range=(2, 4),
            min_df=1,
            sublinear_tf=True,
        )
        texts = [self._doc_to_text(d) for d in self.docs]
        self.tfidf_matrix = self.vectorizer.fit_transform(texts)

    # ── Index building ──────────────────────────────────────────────────────

    def _try_build_embeddings(self):
        global _EMBED_CACHE
        key = _get_api_key()
        if not key:
            return
        try:
            from openai import OpenAI
            client = OpenAI(api_key=key)
            missing = [d for d in self.docs if d["id"] not in _EMBED_CACHE]
            if missing:
                texts = [self._doc_to_text(d) for d in missing]
                resp = client.embeddings.create(
                    model="text-embedding-3-small",
                    input=texts,
                )
                for doc, emb_obj in zip(missing, resp.data):
                    _EMBED_CACHE[doc["id"]] = emb_obj.embedding
            self._use_embeddings = True
        except Exception:
            pass

    def _doc_to_text(self, doc: dict) -> str:
        return " ".join([
            doc.get("title", ""),
            doc.get("age_young", ""),
            doc.get("age_middle", ""),
            doc.get("age_senior", ""),
            doc.get("key_insight", ""),
            doc.get("keywords", ""),
        ])

    # ── Search ──────────────────────────────────────────────────────────────

    def search(self, query: str, top_k: int = 3) -> list[dict]:
        if self._use_embeddings:
            try:
                return self._embed_search(query, top_k)
            except Exception:
                pass
        return self._tfidf_search(query, top_k)

    def _embed_search(self, query: str, top_k: int) -> list[dict]:
        key = _get_api_key()
        if not key:
            raise RuntimeError("no api key")
        from openai import OpenAI
        client = OpenAI(api_key=key)
        resp = client.embeddings.create(model="text-embedding-3-small", input=[query])
        qvec = np.array(resp.data[0].embedding)
        scored = []
        for doc in self.docs:
            emb = _EMBED_CACHE.get(doc["id"])
            if emb is None:
                continue
            scored.append((doc, _cosine(qvec, np.array(emb))))
        scored.sort(key=lambda x: x[1], reverse=True)
        return [d for d, s in scored[:top_k] if s > 0]

    def _tfidf_search(self, query: str, top_k: int) -> list[dict]:
        query_vec = self.vectorizer.transform([query])
        sims = cosine_similarity(query_vec, self.tfidf_matrix)[0]
        top_idx = np.argsort(sims)[::-1][:top_k]
        return [self.docs[i] for i in top_idx if sims[i] > 0]

    # ── Context helpers ─────────────────────────────────────────────────────

    def get_context_for_zone(self, zone_id: str, age_group: str) -> list[dict]:
        doc_ids = ZONE_TO_DOC_IDS.get(zone_id, [])
        matched = [d for d in self.docs if d["id"] in doc_ids]
        if not matched:
            matched = self.search(zone_id, top_k=2)
        return matched

    def get_context_for_prompt(self, world: str, concept: str, age_group: str) -> str:
        docs = self.search(f"{world} {concept}", top_k=3)
        age_key = (
            "age_young"  if age_group == "young"  else
            "age_middle" if age_group == "middle" else
            "age_senior"
        )
        lines = []
        for doc in docs:
            desc = doc.get(age_key) or doc.get("age_middle", "")
            lines.append(f"[{doc['title']}] {desc} (핵심: {doc.get('key_insight', '')})")
        return "\n".join(lines) if lines else concept
