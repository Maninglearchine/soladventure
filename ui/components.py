import streamlit as st

WORLD_COLORS = {
    "dinosaur": "#22c55e",
    "space":    "#6366f1",
    "magic":    "#f59e0b",
    "ocean":    "#0ea5e9",
}


def render_header(character_name: str, coins: int, level: int, world_emoji: str, world_id: str = "dinosaur"):
    color = WORLD_COLORS.get(world_id, "#6366f1")
    r, g, b = tuple(int(color.lstrip("#")[i:i+2], 16) for i in (0, 2, 4))
    st.markdown(
        f"""
        <div style="
            background: rgba(255,255,255,.1);
            backdrop-filter: blur(20px);
            -webkit-backdrop-filter: blur(20px);
            border: 2px solid rgba(255,255,255,.22);
            border-top: 3px solid {color};
            border-radius: 24px;
            padding: 14px 22px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 14px;
            box-shadow: 0 8px 32px rgba(0,0,0,.18), inset 0 1px 0 rgba(255,255,255,.15);
        ">
            <div style="font-size:1.3rem; font-weight:900; color:white; letter-spacing:-.3px;">
                {world_emoji} &nbsp; {character_name or "탐험가"}
            </div>
            <div style="display:flex; gap:18px; align-items:center;">
                <span style="background:rgba(255,214,10,.2);border:1.5px solid rgba(255,214,10,.4);
                    border-radius:100px;padding:5px 14px;font-size:.95rem;font-weight:900;color:#FFE566;">
                    🪙 {coins}</span>
                <span style="background:rgba({r},{g},{b},.2);border:1.5px solid rgba({r},{g},{b},.4);
                    border-radius:100px;padding:5px 14px;font-size:.95rem;font-weight:900;color:{color};">
                    ⭐ Lv.{level}</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_concept_card(concept: str, concept_desc: str, emoji: str):
    st.markdown(
        f"""
        <div style="
            background: rgba(255,255,255,.1);
            backdrop-filter: blur(20px);
            border: 2px solid rgba(255,255,255,.22);
            border-left: 4px solid #FFD60A;
            border-radius: 0 20px 20px 0;
            padding: 16px 20px;
            margin: 12px 0;
            box-shadow: 0 6px 24px rgba(0,0,0,.15);
        ">
            <div style="font-size:1.5rem; margin-bottom:6px;">{emoji} <b style='color:white;font-size:1.05rem;'>{concept}</b></div>
            <div style="font-size:.94rem; color:rgba(255,255,255,.75); line-height:1.7;">{concept_desc}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_mission_result(correct: bool, feedback: str, coins_earned: int):
    if correct:
        bg = "linear-gradient(135deg,rgba(6,214,160,.2),rgba(6,214,160,.1))"
        border_color = "rgba(6,214,160,.5)"
        icon, title = "🎉", "정답이에요!"
        coin_text  = f"+{coins_earned} 코인 획득!"
        coin_color = "#06D6A0"
    else:
        bg = "linear-gradient(135deg,rgba(255,214,10,.15),rgba(255,163,26,.1))"
        border_color = "rgba(255,214,10,.4)"
        icon, title = "💡", "아쉬워요!"
        coin_text  = f"{coins_earned} 코인"
        coin_color = "#FFD60A" if coins_earned >= 0 else "#FF6B6B"

    st.markdown(
        f"""
        <div style="
            background: {bg};
            backdrop-filter: blur(20px);
            border: 2px solid {border_color};
            border-radius: 24px;
            padding: 22px;
            margin: 14px 0;
            text-align: center;
            box-shadow: 0 8px 28px rgba(0,0,0,.18);
        ">
            <div style="font-size:2.5rem;">{icon}</div>
            <div style="font-size:1.3rem; font-weight:900; margin:8px 0; color:white;">{title}</div>
            <div style="font-size:.95rem; color:rgba(255,255,255,.75); margin-bottom:12px; line-height:1.7;">{feedback}</div>
            <div style="font-size:1.2rem; font-weight:900; color:{coin_color};">{coin_text}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_badge(badge_id: str, badge_name: str, emoji: str):
    st.markdown(
        f"""
        <div style="
            background: linear-gradient(135deg, rgba(255,214,10,.22), rgba(255,107,107,.12));
            border: 2px solid rgba(255,214,10,.5);
            border-top: 3px solid rgba(255,214,10,.8);
            border-radius: 20px;
            padding: 14px;
            text-align: center;
            min-width: 100px;
            box-shadow: 0 6px 20px rgba(255,214,10,.2);
        ">
            <div style="font-size:2.2rem; filter:drop-shadow(0 0 8px rgba(255,214,10,.5));">{emoji}</div>
            <div style="font-size:.82rem; font-weight:900; color:#FFE566; margin-top:6px;">{badge_name}</div>
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
                font-size:2.8rem;
                font-weight:900;
                color:#FFD60A;
                padding: 10px;
                filter: drop-shadow(0 0 16px rgba(255,214,10,.6));
                animation: bounce 0.6s ease;
            ">
                🪙 +{amount} 코인!
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f"""
            <div style="text-align:center; font-size:1.9rem; font-weight:900; color:#FF6B6B; padding:10px;
                filter: drop-shadow(0 0 10px rgba(255,107,107,.5));">
                💸 {amount} 코인
            </div>
            """,
            unsafe_allow_html=True,
        )


def render_world_card(world: dict, selected: bool = False) -> bool:
    color = world.get("color", "#6366f1")
    r, g, b = tuple(int(color.lstrip("#")[i:i+2], 16) for i in (0, 2, 4))
    border_top = f"3px solid {color}" if selected else "2px solid rgba(255,255,255,.18)"
    bg = f"rgba({r},{g},{b},.2)" if selected else "rgba(255,255,255,.08)"
    border = f"2px solid rgba({r},{g},{b},.5)" if selected else "2px solid rgba(255,255,255,.15)"
    shadow = f"0 12px 36px rgba({r},{g},{b},.3)" if selected else "0 4px 16px rgba(0,0,0,.12)"
    scale = "scale(1.02)" if selected else "scale(1)"
    st.markdown(
        f"""
        <div style="
            border: {border};
            border-top: {border_top};
            background: {bg};
            backdrop-filter: blur(20px);
            border-radius: 24px;
            padding: 22px 10px;
            text-align: center;
            cursor: pointer;
            transition: all .3s cubic-bezier(.34,1.56,.64,1);
            transform: {scale};
            box-shadow: {shadow};
        ">
            <div style="font-size:3rem; filter:drop-shadow(0 0 10px rgba({r},{g},{b},.4));">{world['emoji']}</div>
            <div style="font-size:1.05rem; font-weight:900; margin:10px 0 4px; color:white;">{world['name']}</div>
            <div style="font-size:.84rem; color:rgba(255,255,255,.65);">{world.get('concept','')}</div>
            <div style="font-size:.8rem; color:rgba(255,255,255,.45); margin-top:6px;">{world.get('description','')}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    return st.button(
        "✓ 선택됨" if selected else "선택하기",
        key=f"world_btn_{world['id']}",
        use_container_width=True,
    )
