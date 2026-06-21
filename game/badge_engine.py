from __future__ import annotations

import streamlit as st

BADGES: list[dict] = [
    {
        "id": "first_step",
        "name": "첫 발걸음",
        "emoji": "👣",
        "desc": "첫 미션 완료",
        "type": "missions_completed",
        "threshold": 1,
    },
    {
        "id": "saver",
        "name": "저축왕",
        "emoji": "🐣",
        "desc": "저축 관련 미션 3개 완료",
        "type": "saving_missions",
        "threshold": 3,
    },
    {
        "id": "investor",
        "name": "투자 탐험가",
        "emoji": "🚀",
        "desc": "투자 관련 미션 3개 완료",
        "type": "invest_missions",
        "threshold": 3,
    },
    {
        "id": "budget_master",
        "name": "용돈 마스터",
        "emoji": "🧙",
        "desc": "용돈 관련 미션 3개 완료",
        "type": "budget_missions",
        "threshold": 3,
    },
    {
        "id": "interest_wizard",
        "name": "이자 마법사",
        "emoji": "🐠",
        "desc": "이자/복리 미션 3개 완료",
        "type": "interest_missions",
        "threshold": 3,
    },
    {
        "id": "accuracy_star",
        "name": "정확쟁이",
        "emoji": "⭐",
        "desc": "정답률 80% 이상",
        "type": "accuracy",
        "threshold": 80,
    },
    {
        "id": "explorer",
        "name": "세계 탐험가",
        "emoji": "🌍",
        "desc": "2개 이상 세계에서 미션 완료",
        "type": "worlds_visited",
        "threshold": 2,
    },
    {
        "id": "coin_master",
        "name": "코인 부자",
        "emoji": "💰",
        "desc": "코인 200개 이상 보유",
        "type": "coins",
        "threshold": 200,
    },
]

_SAVING_ZONES = {"savings_cave", "goal_tree", "trade_market"}
_INVEST_ZONES = {"invest_planet", "risk_asteroid", "diversify_galaxy"}
_BUDGET_ZONES = {"budget_castle", "needs_market", "impulse_cave"}
_INTEREST_ZONES = {"interest_reef", "compound_trench", "longterm_palace"}
_ALL_ZONES = _SAVING_ZONES | _INVEST_ZONES | _BUDGET_ZONES | _INTEREST_ZONES


class BadgeEngine:

    # ── Metrics ──────────────────────────────────────────────────────────────

    def _get_metrics(self, game_state) -> dict:
        completed: set[str] = set(game_state.completed_missions)

        saving = sum(1 for m in completed if m.startswith("dino_"))
        invest = sum(1 for m in completed if m.startswith("space_"))
        budget = sum(1 for m in completed if m.startswith("magic_"))
        interest = sum(1 for m in completed if m.startswith("ocean_"))

        for zone_id in _SAVING_ZONES:
            if st.session_state.get(f"dynamic_done_{zone_id}"):
                saving += 1
        for zone_id in _INVEST_ZONES:
            if st.session_state.get(f"dynamic_done_{zone_id}"):
                invest += 1
        for zone_id in _BUDGET_ZONES:
            if st.session_state.get(f"dynamic_done_{zone_id}"):
                budget += 1
        for zone_id in _INTEREST_ZONES:
            if st.session_state.get(f"dynamic_done_{zone_id}"):
                interest += 1

        worlds_visited = sum([saving > 0, invest > 0, budget > 0, interest > 0])

        dynamic_total = sum(
            1 for z in _ALL_ZONES if st.session_state.get(f"dynamic_done_{z}")
        )
        missions_completed = len(completed) + dynamic_total

        history = st.session_state.get("_answer_history", [])
        accuracy = (
            sum(1 for h in history if h["correct"]) / len(history) * 100
            if history else 0
        )

        return {
            "missions_completed": missions_completed,
            "saving_missions": saving,
            "invest_missions": invest,
            "budget_missions": budget,
            "interest_missions": interest,
            "accuracy": accuracy,
            "worlds_visited": worlds_visited,
            "coins": game_state.coins,
        }

    # ── Public API ───────────────────────────────────────────────────────────

    def check_and_award(self, game_state) -> list[dict]:
        metrics = self._get_metrics(game_state)
        newly_awarded: list[dict] = []

        for badge in BADGES:
            if badge["id"] in game_state.badges:
                continue
            current = metrics.get(badge["type"], 0)
            if current >= badge["threshold"]:
                game_state.unlock_badge(badge["id"])
                newly_awarded.append(badge)

        return newly_awarded

    def get_earned_badges(self, game_state) -> list[dict]:
        return [b for b in BADGES if b["id"] in game_state.badges]

    def get_next_badge(self, game_state) -> dict | None:
        metrics = self._get_metrics(game_state)
        unearned = [b for b in BADGES if b["id"] not in game_state.badges]
        if not unearned:
            return None

        def progress_pct(badge: dict) -> float:
            threshold = badge["threshold"]
            if threshold <= 0:
                return 1.0
            return min(1.0, metrics.get(badge["type"], 0) / threshold)

        return max(unearned, key=progress_pct)

    def badge_progress_pct(self, badge: dict, game_state) -> float:
        metrics = self._get_metrics(game_state)
        threshold = badge["threshold"]
        if threshold <= 0:
            return 1.0
        return min(1.0, metrics.get(badge["type"], 0) / threshold)

    def get_metrics(self, game_state) -> dict:
        return self._get_metrics(game_state)
