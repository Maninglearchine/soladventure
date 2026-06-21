import streamlit as st

WORLD_COLORS = {
    "dinosaur": "#22c55e",
    "space": "#6366f1",
    "magic": "#f59e0b",
    "ocean": "#0ea5e9",
}


def render_header(character_name: str, coins: int, level: int, world_emoji: str, world_id: str = "dinosaur"):
    color = WORLD_COLORS.get(world_id, "#6366f1")
    st.markdown(
        f"""
        <div style="
            background: linear-gradient(135deg, {color}22, {color}44);
            border: 2px solid {color};
            border-radius: 16px;
            padding: 12px 20px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 12px;
        ">
            <div style="font-size:1.4rem; font-weight:700;">
                {world_emoji} &nbsp; {character_name or "탐험가"}
            </div>
            <div style="display:flex; gap:24px; font-size:1.1rem; font-weight:600;">
                <span>🪙 {coins} 코인</span>
                <span>⭐ Lv.{level}</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_concept_card(concept: str, concept_desc: str, emoji: str):
    st.markdown(
        f"""
        <div style="
            background: #eff6ff;
            border-left: 5px solid #3b82f6;
            border-radius: 10px;
            padding: 14px 18px;
            margin: 10px 0;
        ">
            <div style="font-size:1.5rem; margin-bottom:4px;">{emoji} <b>{concept}</b></div>
            <div style="font-size:1rem; color:#1e40af;">{concept_desc}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_mission_result(correct: bool, feedback: str, coins_earned: int):
    if correct:
        color, icon, title = "#dcfce7", "🎉", "정답이에요!"
        coin_text = f"+{coins_earned} 코인 획득!"
        coin_color = "#16a34a"
    else:
        color, icon, title = "#fef9c3", "💡", "아쉬워요!"
        coin_text = f"{coins_earned} 코인" if coins_earned >= 0 else f"{coins_earned} 코인"
        coin_color = "#b45309" if coins_earned < 0 else "#92400e"

    st.markdown(
        f"""
        <div style="
            background: {color};
            border-radius: 14px;
            padding: 18px 22px;
            margin: 14px 0;
            text-align: center;
        ">
            <div style="font-size:2rem;">{icon}</div>
            <div style="font-size:1.3rem; font-weight:700; margin:6px 0;">{title}</div>
            <div style="font-size:1rem; color:#374151; margin-bottom:10px;">{feedback}</div>
            <div style="font-size:1.2rem; font-weight:700; color:{coin_color};">{coin_text}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_badge(badge_id: str, badge_name: str, emoji: str):
    st.markdown(
        f"""
        <div style="
            background: linear-gradient(135deg, #fef3c7, #fde68a);
            border: 2px solid #f59e0b;
            border-radius: 12px;
            padding: 12px;
            text-align: center;
            min-width: 100px;
        ">
            <div style="font-size:2rem;">{emoji}</div>
            <div style="font-size:0.85rem; font-weight:600; color:#92400e; margin-top:4px;">{badge_name}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_coin_animation(amount: int):
    if amount > 0:
        st.balloons()
        st.markdown(
            f"""
            <div style="
                text-align:center;
                font-size:2.5rem;
                font-weight:900;
                color:#f59e0b;
                animation: none;
                padding: 8px;
            ">
                🪙 +{amount} 코인!
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f"""
            <div style="text-align:center; font-size:1.8rem; font-weight:700; color:#ef4444; padding:8px;">
                💸 {amount} 코인
            </div>
            """,
            unsafe_allow_html=True,
        )


def render_world_card(world: dict, selected: bool = False) -> bool:
    border = f"3px solid {world['color']}" if selected else "2px solid #e5e7eb"
    bg = f"{world['color']}18" if selected else "#ffffff"
    st.markdown(
        f"""
        <div style="
            border: {border};
            background: {bg};
            border-radius: 16px;
            padding: 20px 10px;
            text-align: center;
            cursor: pointer;
            transition: all 0.2s;
        ">
            <div style="font-size:3rem;">{world['emoji']}</div>
            <div style="font-size:1.1rem; font-weight:700; margin:8px 0 4px;">{world['name']}</div>
            <div style="font-size:0.85rem; color:#6b7280;">{world['concept']}</div>
            <div style="font-size:0.8rem; color:#9ca3af; margin-top:6px;">{world['description']}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    return st.button(
        "✓ 선택됨" if selected else "선택하기",
        key=f"world_btn_{world['id']}",
        use_container_width=True,
    )
