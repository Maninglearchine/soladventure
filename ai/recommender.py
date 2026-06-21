from __future__ import annotations

import streamlit as st


class MissionRecommender:
    _HISTORY_KEY = "_answer_history"

    def __init__(self):
        if self._HISTORY_KEY not in st.session_state:
            st.session_state[self._HISTORY_KEY] = []

    # ── Core history ────────────────────────────────────────────────────────

    @property
    def history(self) -> list[dict]:
        return st.session_state.get(self._HISTORY_KEY, [])

    def log_answer(self, zone_id: str, concept: str, correct: bool):
        st.session_state[self._HISTORY_KEY] = self.history + [
            {"zone_id": zone_id, "concept": concept, "correct": correct}
        ]

    def get_accuracy(self) -> float:
        h = self.history
        if not h:
            return 0.5
        return sum(1 for x in h if x["correct"]) / len(h)

    # ── Recommendations ─────────────────────────────────────────────────────

    def recommend_difficulty(self, game_state) -> str:
        acc = self.get_accuracy()
        if acc < 0.5:
            return "easy"
        elif acc <= 0.8:
            return "medium"
        return "hard"

    def recommend_next_zone(self, game_state, world_zones: list[dict]) -> dict:
        h = self.history
        weak_zone_ids = {x["zone_id"] for x in h if not x["correct"]}

        completed = set()
        for mid in game_state.completed_missions:
            for zone in world_zones:
                if zone["id"] in mid:
                    completed.add(zone["id"])

        def score(zone: dict, idx: int) -> int:
            s = 0
            zid = zone["id"]
            if zid not in completed:
                s += 10
            if zid in weak_zone_ids:
                s += 5
            s += max(0, 3 - idx)
            if zid in completed:
                s -= 20
            return s

        return max(world_zones, key=lambda z: score(z, world_zones.index(z)))

    # ── Stats ────────────────────────────────────────────────────────────────

    def concept_accuracy(self) -> dict[str, dict]:
        """Returns {concept: {correct: int, total: int}} for chart rendering."""
        result: dict[str, dict] = {}
        for entry in self.history:
            c = entry["concept"]
            if c not in result:
                result[c] = {"correct": 0, "total": 0}
            result[c]["total"] += 1
            if entry["correct"]:
                result[c]["correct"] += 1
        return result

    def reset(self):
        st.session_state[self._HISTORY_KEY] = []
