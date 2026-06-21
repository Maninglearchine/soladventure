from __future__ import annotations

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from ai.finance_docs import FINANCE_DOCS, ZONE_TO_DOC_IDS


class RAGEngine:
    def __init__(self):
        self.docs = FINANCE_DOCS
        self.vectorizer = TfidfVectorizer(
            analyzer="char_wb",
            ngram_range=(2, 4),
            min_df=1,
            sublinear_tf=True,
        )
        self._build_index()

    def _build_index(self):
        texts = [self._doc_to_text(d) for d in self.docs]
        self.tfidf_matrix = self.vectorizer.fit_transform(texts)

    def _doc_to_text(self, doc: dict) -> str:
        return " ".join([
            doc.get("title", ""),
            doc.get("age_young", ""),
            doc.get("age_middle", ""),
            doc.get("age_senior", ""),
            doc.get("key_insight", ""),
            doc.get("keywords", ""),
        ])

    def search(self, query: str, top_k: int = 3) -> list[dict]:
        query_vec = self.vectorizer.transform([query])
        sims = cosine_similarity(query_vec, self.tfidf_matrix)[0]
        top_idx = np.argsort(sims)[::-1][:top_k]
        return [self.docs[i] for i in top_idx if sims[i] > 0]

    def get_context_for_zone(self, zone_id: str, age_group: str) -> list[dict]:
        doc_ids = ZONE_TO_DOC_IDS.get(zone_id, [])
        matched = [d for d in self.docs if d["id"] in doc_ids]
        if not matched:
            matched = self.search(zone_id, top_k=2)
        return matched

    def get_context_for_prompt(self, world: str, concept: str, age_group: str) -> str:
        docs = self.search(f"{world} {concept}", top_k=3)
        age_key = "age_young" if age_group == "young" else "age_middle" if age_group == "middle" else "age_senior"
        lines = []
        for doc in docs:
            desc = doc.get(age_key) or doc.get("age_middle", "")
            lines.append(f"[{doc['title']}] {desc} (핵심: {doc.get('key_insight', '')})")
        return "\n".join(lines) if lines else concept
