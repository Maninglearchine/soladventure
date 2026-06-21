import streamlit as st


class GameState:
    DEFAULTS = {
        "world": None,
        "character_name": "",
        "character_color": "#22c55e",
        "age_group": "all",
        "coins": 50,
        "level": 1,
        "completed_missions": [],
        "badges": [],
        "current_zone": None,
        "player_x": 0,
        "player_y": 0,
        "page": "onboarding",
        "current_mission_idx": 0,
        "mission_answered": False,
        "last_answer": None,
        "coin_log": [],
    }

    def __init__(self):
        for key, value in self.DEFAULTS.items():
            if key not in st.session_state:
                st.session_state[key] = value if not isinstance(value, list) else list(value)

    def __getattr__(self, key):
        if key in self.DEFAULTS:
            return st.session_state.get(key, self.DEFAULTS[key])
        raise AttributeError(key)

    def __setattr__(self, key, value):
        if key in self.DEFAULTS:
            st.session_state[key] = value
        else:
            super().__setattr__(key, value)

    # ── Coins ─────────────────────────────────────────────────────────────────

    def add_coins(self, amount: int, label: str = ""):
        new_total = max(0, st.session_state.coins + amount)
        st.session_state.coins = new_total
        if amount != 0:
            entry = {
                "label": label or "미션",
                "delta": amount,
                "total": new_total,
            }
            st.session_state.coin_log = st.session_state.coin_log + [entry]

    # ── Missions ──────────────────────────────────────────────────────────────

    def complete_mission(self, mission_id: str):
        if mission_id not in st.session_state.completed_missions:
            st.session_state.completed_missions = (
                st.session_state.completed_missions + [mission_id]
            )

    # ── Level (mission-based: 3 missions per level) ───────────────────────────

    def recalculate_level(self) -> tuple:
        dynamic_done = sum(
            1 for k, v in st.session_state.items()
            if isinstance(k, str) and k.startswith("dynamic_done_") and v
        )
        total = len(st.session_state.completed_missions) + dynamic_done
        new_level = max(1, total // 3 + 1)
        old_level = st.session_state.level
        if new_level > old_level:
            st.session_state.level = new_level
            return new_level, True
        return old_level, False

    def level_xp_progress(self) -> tuple:
        """Returns (missions_in_current_level, missions_per_level)."""
        dynamic_done = sum(
            1 for k, v in st.session_state.items()
            if isinstance(k, str) and k.startswith("dynamic_done_") and v
        )
        total = len(st.session_state.completed_missions) + dynamic_done
        return total % 3, 3

    # ── Badges ────────────────────────────────────────────────────────────────

    def unlock_badge(self, badge_id: str):
        if badge_id not in st.session_state.badges:
            st.session_state.badges = st.session_state.badges + [badge_id]

    # ── Navigation ────────────────────────────────────────────────────────────

    def move_player(self, dx: int, dy: int):
        st.session_state.player_x = max(0, min(2, st.session_state.player_x + dx))
        st.session_state.player_y = max(0, min(0, st.session_state.player_y + dy))

    def go_to(self, page: str):
        st.session_state.page = page

    # ── Progress ──────────────────────────────────────────────────────────────

    def get_progress_pct(self) -> float:
        dynamic_done = sum(
            1 for k, v in st.session_state.items()
            if isinstance(k, str) and k.startswith("dynamic_done_") and v
        )
        total = len(st.session_state.completed_missions) + dynamic_done
        return min(1.0, total / 12)

    # ── Reset ─────────────────────────────────────────────────────────────────

    def reset(self):
        for key, value in self.DEFAULTS.items():
            st.session_state[key] = value if not isinstance(value, list) else list(value)
        for k in list(st.session_state.keys()):
            if isinstance(k, str) and k.startswith("dynamic_done_"):
                del st.session_state[k]
        if "_answer_history" in st.session_state:
            st.session_state["_answer_history"] = []
