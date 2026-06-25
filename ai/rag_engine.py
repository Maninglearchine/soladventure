from __future__ import annotations

import os

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from ai.finance_docs import FINANCE_DOCS, ZONE_TO_DOC_IDS

# Module-level embedding cache — {chunk_id: list[float]}
# Survives across QuizGenerator re-instantiations within the same process.
_EMBED_CACHE: dict[str, list[float]] = {}

_AGE_KEYS = ["age_young", "age_middle", "age_senior"]


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


def _base_text(doc: dict) -> str:
    """title + keywords + key_insight — 모든 청크에 공통으로 overlap되는 베이스."""
    return " ".join(filter(None, [
        doc.get("title", ""),
        doc.get("keywords", ""),
        doc.get("key_insight", ""),
    ]))


def _make_chunks(doc: dict) -> list[dict]:
    """
    문서 1개를 연령별 청크 3개로 분할.
    각 청크는 base(title+keywords+key_insight)를 공통으로 포함(overlap)하고
    해당 연령 설명을 이어 붙인다.
    연령 설명이 없는 경우 전체 합산 청크 1개를 대신 사용.
    """
    base = _base_text(doc)
    chunks = []
    for age_key in _AGE_KEYS:
        age_text = doc.get(age_key, "").strip()
        if not age_text:
            continue
        chunks.append({
            "chunk_id":  f"{doc['id']}_{age_key}",
            "doc_id":    doc["id"],
            "age_key":   age_key,
            "text":      f"{base} {age_text}",   # base가 overlap으로 포함
            "_doc":      doc,
        })
    # 연령 청크가 하나도 없으면 전체 합산 청크
    if not chunks:
        all_text = " ".join(filter(None, [
            base,
            doc.get("age_young", ""),
            doc.get("age_middle", ""),
            doc.get("age_senior", ""),
        ]))
        chunks.append({
            "chunk_id": f"{doc['id']}_full",
            "doc_id":   doc["id"],
            "age_key":  None,
            "text":     all_text,
            "_doc":     doc,
        })
    return chunks


class RAGEngine:
    def __init__(self):
        self.docs = FINANCE_DOCS

        # 연령별 청크 목록 (모든 문서의 청크를 평탄화)
        self.chunks: list[dict] = []
        for doc in self.docs:
            self.chunks.extend(_make_chunks(doc))

        self._use_embeddings = False
        self._try_build_embeddings()

        # TF-IDF 인덱스 — 청크 단위로 구축 (폴백용)
        self.vectorizer = TfidfVectorizer(
            analyzer="char_wb",
            ngram_range=(2, 4),
            min_df=1,
            sublinear_tf=True,
        )
        self.tfidf_matrix = self.vectorizer.fit_transform(
            [c["text"] for c in self.chunks]
        )

    # ── Index building ──────────────────────────────────────────────────────

    def _try_build_embeddings(self):
        global _EMBED_CACHE
        key = _get_api_key()
        if not key:
            return
        try:
            from openai import OpenAI
            client = OpenAI(api_key=key)
            missing = [c for c in self.chunks if c["chunk_id"] not in _EMBED_CACHE]
            if missing:
                texts = [c["text"] for c in missing]
                resp = client.embeddings.create(
                    model="text-embedding-3-small",
                    input=texts,
                )
                for chunk, emb_obj in zip(missing, resp.data):
                    _EMBED_CACHE[chunk["chunk_id"]] = emb_obj.embedding
            self._use_embeddings = True
        except Exception:
            pass

    # ── Search ──────────────────────────────────────────────────────────────

    def search(self, query: str, top_k: int = 3, age_group: str | None = None) -> list[dict]:
        """
        age_group을 넘기면 해당 연령 청크를 우선 반환.
        중복 문서는 제거하고 최대 top_k개의 고유 문서를 반환.
        """
        age_key = (
            "age_young"  if age_group == "young"  else
            "age_middle" if age_group == "middle" else
            "age_senior" if age_group == "senior" else
            None
        )

        if self._use_embeddings:
            try:
                return self._embed_search(query, top_k, age_key)
            except Exception:
                pass
        return self._tfidf_search(query, top_k, age_key)

    def _embed_search(self, query: str, top_k: int, age_key: str | None) -> list[dict]:
        key = _get_api_key()
        if not key:
            raise RuntimeError("no api key")
        from openai import OpenAI
        client = OpenAI(api_key=key)
        resp = client.embeddings.create(model="text-embedding-3-small", input=[query])
        qvec = np.array(resp.data[0].embedding)

        scored: list[tuple[dict, float]] = []
        for chunk in self.chunks:
            emb = _EMBED_CACHE.get(chunk["chunk_id"])
            if emb is None:
                continue
            score = _cosine(qvec, np.array(emb))
            # 연령 일치 청크에 가중치 부여
            if age_key and chunk["age_key"] == age_key:
                score *= 1.25
            scored.append((chunk, score))

        scored.sort(key=lambda x: x[1], reverse=True)
        return self._dedup_docs(scored, top_k)

    def _tfidf_search(self, query: str, top_k: int, age_key: str | None) -> list[dict]:
        query_vec = self.vectorizer.transform([query])
        sims = cosine_similarity(query_vec, self.tfidf_matrix)[0]

        # 연령 일치 청크에 가중치 부여
        if age_key:
            for i, chunk in enumerate(self.chunks):
                if chunk["age_key"] == age_key:
                    sims[i] *= 1.25

        top_idx = np.argsort(sims)[::-1]
        scored = [(self.chunks[i], sims[i]) for i in top_idx if sims[i] > 0]
        return self._dedup_docs(scored, top_k)

    @staticmethod
    def _dedup_docs(scored: list[tuple[dict, float]], top_k: int) -> list[dict]:
        """청크 점수 순으로 정렬 후 동일 문서의 중복을 제거해 고유 문서 반환."""
        seen: set[str] = set()
        result: list[dict] = []
        for chunk, _ in scored:
            doc_id = chunk["doc_id"]
            if doc_id not in seen:
                seen.add(doc_id)
                result.append(chunk["_doc"])
            if len(result) >= top_k:
                break
        return result

    # ── Context helpers ─────────────────────────────────────────────────────

    def get_context_for_zone(self, zone_id: str, age_group: str) -> list[dict]:
        doc_ids = ZONE_TO_DOC_IDS.get(zone_id, [])
        matched = [d for d in self.docs if d["id"] in doc_ids]
        if not matched:
            matched = self.search(zone_id, top_k=2, age_group=age_group)
        return matched

    def get_context_for_prompt(self, world: str, concept: str, age_group: str) -> str:
        docs = self.search(f"{world} {concept}", top_k=3, age_group=age_group)
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
