"""
Parent Report Page — 4-tab breakdown of today's financial learning.
"""
from __future__ import annotations

import json
import math
import os

import plotly.graph_objects as go
import streamlit as st

from ui.portfolio_chart import PortfolioChart, WORLD_COLORS

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ── Static product cards ─────────────────────────────────────────────────────

_PRODUCT_CARDS = [
    {
        "name": "우리아이통장",
        "type": "아이 명의 자유적금",
        "emoji": "🐣",
        "color": "#22c55e",
        "features": [
            "만 0~18세 자녀 명의로 개설 가능",
            "자유로운 입출금 + 우대금리 제공",
            "금융 교육 콘텐츠 연계 서비스",
        ],
        "note": "※ 본 안내는 투자 권유가 아닌 정보 제공 목적입니다.",
    },
    {
        "name": "우리아이 펀드 만들기",
        "type": "비대면 미성년 전용 펀드",
        "emoji": "🚀",
        "color": "#6366f1",
        "features": [
            "부모 대리 신청 비대면 가입 가능",
            "분산 투자 포트폴리오 자동 구성",
            "장기 투자 습관 형성에 최적화",
        ],
        "note": "※ 투자 원금 손실이 발생할 수 있습니다. 과거 수익률이 미래 수익을 보장하지 않습니다.",
    },
]


# ── Helpers ──────────────────────────────────────────────────────────────────

def _load_missions() -> list:
    try:
        with open(os.path.join(BASE, "data", "missions.json"), encoding="utf-8") as f:
            return json.load(f)["missions"]
    except Exception:
        return []


def _get_learned_concepts(gs, missions: list) -> list[dict]:
    """Map completed mission IDs → concept_card dicts (deduped)."""
    done_ids = set(gs.completed_missions)
    seen, result = set(), []
    for m in missions:
        if m.get("id") not in done_ids:
            continue
        cc = m.get("concept_card", {})
        title = cc.get("title") or cc.get("concept", "")
        if title and title not in seen:
            seen.add(title)
            result.append({
                "title": title,
                "emoji": cc.get("emoji", "💡"),
                "body":  cc.get("body",  ""),
            })
    # Also pick up concepts from Phaser NPC quizzes stored in session state quizzes
    for q in (st.session_state.get(f"_quizzes_{gs.world}") or []):
        cc = q.get("concept_card", {})
        title = cc.get("title", "")
        if title and title not in seen:
            seen.add(title)
            result.append({
                "title": title,
                "emoji": cc.get("emoji", "🎮"),
                "body":  cc.get("body",  ""),
            })
    return result


def _get_weak_concepts(history: list) -> list[str]:
    """Concepts with correct-rate < 60 %."""
    from collections import defaultdict
    counts: dict = defaultdict(lambda: [0, 0])  # [correct, total]
    for h in history:
        c = h.get("concept", "")
        if not c:
            continue
        counts[c][1] += 1
        if h.get("correct"):
            counts[c][0] += 1
    return [
        c for c, (correct, total) in counts.items()
        if total >= 1 and correct / total < 0.6
    ]


def _generate_parent_text(gs, concepts: list, generator) -> str:
    """Call OpenAI to generate a warm parent-facing report."""
    concept_names = ", ".join(c["title"] for c in concepts[:6]) if concepts else "금융 기초 개념"

    # Try to get OpenAI client from generator or directly
    client = None
    try:
        if hasattr(generator, "_client"):
            client = generator._client
    except Exception:
        pass
    if client is None:
        try:
            import os as _os
            from openai import OpenAI
            key = st.session_state.get("openai_api_key") or _os.environ.get("OPENAI_API_KEY")
            if key:
                client = OpenAI(api_key=key)
        except ImportError:
            pass

    if client is None:
        return _default_parent_text(gs, concepts)

    age_label = {"young": "6~8세", "middle": "9~11세", "all": "12~13세"}.get(
        gs.age_group, gs.age_group
    )
    prompt = f"""
아이({gs.character_name}, {age_label})가 핀퀘스트에서 아래 금융 개념을 배웠어요:
{concept_names}

부모에게 200자 이내로:
1. 아이가 오늘 잘 이해한 개념
2. 실생활에서 아이와 함께 실천할 수 있는 팁 1가지
3. 관련 금융 습관 형성에 도움되는 한 마디

투자 권유 표현 금지. 따뜻한 어조로.
""".strip()

    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=420,
        )
        return resp.choices[0].message.content
    except Exception:
        return _default_parent_text(gs, concepts)


def _default_parent_text(gs, concepts: list) -> str:
    name = gs.character_name or "아이"
    c_str = ", ".join(c["title"] for c in concepts[:3]) if concepts else "금융 기초 개념"
    return (
        f"오늘 {name}이(가) **{c_str}**에 대해 열심히 배웠어요! 🎉\n\n"
        f"저축통에 용돈을 나눠 담는 간단한 활동으로 오늘 배운 개념을 생활 속에서 실천해보세요. "
        f"작은 습관이 아이의 경제적 미래를 밝게 만들어 줍니다 🌟"
    )


# ── Monthly savings compound chart ───────────────────────────────────────────

def _monthly_compound_chart(world_id: str) -> go.Figure:
    """Bar chart: save 10,000원/month at 3% for 10/20/30 years."""
    color = WORLD_COLORS.get(world_id, "#0ea5e9")
    monthly, rate = 10_000, 0.03
    r12 = rate / 12

    years_list = [10, 20, 30]
    compound = [
        round(monthly * ((1 + r12) ** (y * 12) - 1) / r12)
        for y in years_list
    ]
    simple = [monthly * 12 * y for y in years_list]
    labels = [f"{y}년" for y in years_list]

    fig = go.Figure()
    r, g, b = tuple(int(color.lstrip("#")[i:i+2], 16) for i in (0, 2, 4))
    fig.add_trace(go.Bar(
        name="단순 저축", x=labels, y=simple,
        marker_color=f"rgba({r},{g},{b},0.35)",
        hovertemplate="%{x}: %{y:,.0f}원<extra>단순 저축</extra>",
    ))
    fig.add_trace(go.Bar(
        name="복리 저축 (3%)", x=labels, y=compound,
        marker_color=color,
        hovertemplate="%{x}: %{y:,.0f}원<extra>복리</extra>",
    ))
    fig.add_annotation(
        x="30년", y=compound[-1],
        text=f"복리: {compound[-1]/10000:,.0f}만원!",
        showarrow=True, arrowhead=2, arrowcolor=color,
        font=dict(size=11, color=color), bgcolor="white",
        bordercolor=color, borderwidth=1,
    )
    fig.update_layout(
        barmode="group", height=320,
        margin=dict(l=10, r=10, t=50, b=10),
        xaxis=dict(title="저축 기간"),
        yaxis=dict(title="금액 (원)", showgrid=True, gridcolor="#f3f4f6"),
        paper_bgcolor="white", plot_bgcolor="white",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        title=dict(
            text="💡 매달 10,000원씩 저축하면? (연 3% 복리 기준)",
            font=dict(size=14), x=0.5,
        ),
    )
    return fig


# ── Tab renderers ────────────────────────────────────────────────────────────

def _tab_learning(gs, concepts: list, history: list, badge_engine):
    st.markdown(f"### 📚 {gs.character_name or '탐험가'}의 오늘 학습 요약")

    # ── 3 metric cards ──
    dynamic_done = sum(
        1 for k, v in st.session_state.items()
        if isinstance(k, str) and k.startswith("dynamic_done_") and v
    )
    total_done  = len(gs.completed_missions) + dynamic_done
    accuracy    = (
        sum(1 for h in history if h.get("correct")) / len(history) * 100
        if history else 0
    )

    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("✅ 완료 미션", f"{total_done}개")
    with c2:
        st.metric("💰 코인 잔액", f"{gs.coins}")
    with c3:
        st.metric("🎯 정답률", f"{accuracy:.0f}%")

    st.divider()

    # ── Concepts learned ──
    if concepts:
        st.markdown("#### 📖 오늘 배운 금융 개념")
        for c in concepts:
            st.markdown(
                f"""<div style="display:flex;align-items:center;gap:8px;
                    padding:7px 12px;margin-bottom:5px;
                    background:#f8fafc;border-radius:8px;border-left:3px solid #22c55e;">
                    <span style="font-size:1.3rem;">{c['emoji']}</span>
                    <div><b>{c['title']}</b>
                    {"<br><span style='font-size:0.82rem;color:#6b7280;'>" + c['body'] + "</span>" if c['body'] else ""}
                    </div></div>""",
                unsafe_allow_html=True,
            )
    else:
        st.info("아직 완료된 미션이 없어요. 탐험을 시작해봐요! 🗺️")

    # ── Weak concepts ──
    weak = _get_weak_concepts(history)
    if weak:
        st.divider()
        st.markdown("#### 🔁 다음엔 이 개념을 더 연습해요!")
        for w in weak:
            st.warning(f"💡 **{w}** — 한 번 더 도전해봐요!")

    st.divider()

    # ── Concept radar ──
    chart = PortfolioChart()
    scores = chart.build_concept_scores(history)
    if any(v > 0 for v in scores.values()):
        st.markdown("#### 🧠 금융 개념 이해도 레이더")
        fig = chart.render_concept_radar(scores, gs.world or "ocean")
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


def _tab_assets(gs, history: list):
    world_id = gs.world or "ocean"
    coin_log  = st.session_state.get("coin_log", [])
    chart     = PortfolioChart()

    st.markdown("### 📈 코인 누적 기록")
    fig_hist = chart.render_coin_history(coin_log, world_id)
    st.plotly_chart(fig_hist, use_container_width=True, config={"displayModeBar": False})

    st.divider()
    st.markdown("### 💰 복리 성장 시뮬레이션")
    st.caption("아이가 매달 10,000원씩 저축하면 얼마나 불어날까요? (연 3% 복리 기준)")
    fig_sim = _monthly_compound_chart(world_id)
    st.plotly_chart(fig_sim, use_container_width=True, config={"displayModeBar": False})

    # Quick comparison call-out
    r12 = 0.03 / 12
    comp_30 = round(10_000 * ((1 + r12) ** 360 - 1) / r12)
    simp_30 = 10_000 * 12 * 30
    extra   = comp_30 - simp_30
    st.success(
        f"💡 30년 복리 저축이면 단순 저축보다 **{extra:,}원** 더 모을 수 있어요!"
    )


def _tab_badges(gs, badge_engine):
    chart = PortfolioChart()
    chart.render_badge_progress(badge_engine, gs)

    next_b = badge_engine.get_next_badge(gs)
    if next_b:
        pct = badge_engine.badge_progress_pct(next_b, gs)
        st.divider()
        st.markdown("#### 🎯 다음 목표 뱃지")
        st.markdown(
            f"""<div style="background:#f0fdf4;border:2px solid #22c55e;
                border-radius:12px;padding:16px;text-align:center;">
                <div style="font-size:2.5rem;">{next_b['emoji']}</div>
                <div style="font-size:1.1rem;font-weight:700;margin:6px 0;">{next_b['name']}</div>
                <div style="font-size:0.9rem;color:#166534;">{next_b['desc']}</div>
                <div style="font-size:0.85rem;color:#6b7280;margin-top:8px;">달성까지 {pct:.0%}</div>
            </div>""",
            unsafe_allow_html=True,
        )
        st.progress(pct)

    from game.badge_engine import BADGES
    earned = len(gs.badges)
    total  = len(BADGES)
    st.divider()
    st.markdown(f"**전체 뱃지 달성률:** {earned} / {total}  ({earned/total:.0%})")
    st.progress(earned / total)


def _tab_products(gs, concepts: list, generator):
    st.markdown("### 👨‍👩‍👧 부모님께 드리는 맞춤 안내")

    # Auto-generate AI report (cached in session state)
    cache_key = "_parent_report_text"
    if not st.session_state.get(cache_key):
        with st.spinner("🤖 AI 리포트를 작성 중이에요..."):
            st.session_state[cache_key] = _generate_parent_text(gs, concepts, generator)

    report_md = st.session_state[cache_key]
    st.markdown(
        f"""<div style="background:#f0fdf4;border-left:4px solid #22c55e;
            border-radius:10px;padding:14px 18px;margin-bottom:12px;
            font-size:0.95rem;line-height:1.7;color:#1a3a1a;">
            {report_md.replace(chr(10),'<br>')}
        </div>""",
        unsafe_allow_html=True,
    )
    if st.button("🔄 리포트 다시 생성", key="regen_report"):
        st.session_state.pop(cache_key, None)
        st.rerun()

    st.divider()
    st.markdown("### 💳 추천 금융상품 안내")
    st.caption("아이의 학습 결과를 바탕으로 참고할 만한 금융 상품을 소개해드려요.")

    p1, p2 = st.columns(2)
    for col, prod in zip([p1, p2], _PRODUCT_CARDS):
        with col:
            r, g, b = tuple(int(prod["color"].lstrip("#")[i:i+2], 16) for i in (0, 2, 4))
            feats_html = "".join(f"<li style='margin:4px 0;'>{f}</li>" for f in prod["features"])
            st.markdown(
                f"""<div style="border:2px solid {prod['color']};border-radius:16px;
                    padding:18px;background:rgba({r},{g},{b},0.06);height:100%;">
                    <div style="font-size:2rem;text-align:center;">{prod['emoji']}</div>
                    <div style="font-size:1.05rem;font-weight:700;text-align:center;
                        margin:8px 0 4px;color:{prod['color']};">{prod['name']}</div>
                    <div style="font-size:0.82rem;color:#6b7280;text-align:center;
                        margin-bottom:12px;">{prod['type']}</div>
                    <ul style="font-size:0.88rem;color:#374151;padding-left:18px;margin:0;">
                        {feats_html}
                    </ul>
                    <div style="font-size:0.72rem;color:#9ca3af;margin-top:12px;">
                        {prod['note']}
                    </div>
                </div>""",
                unsafe_allow_html=True,
            )

    st.divider()
    st.caption(
        "⚠️ **면책 고지:** 본 안내는 투자 권유가 아닌 정보 제공 목적입니다. "
        "금융상품 가입 전 각 금융기관의 약관 및 설명서를 반드시 확인하시기 바랍니다."
    )


# ── Public entry point ────────────────────────────────────────────────────────

def render_parent_report(gs, scenario_generator, badge_engine, recommender=None):
    world_id = gs.world or "ocean"
    missions  = _load_missions()
    concepts  = _get_learned_concepts(gs, missions)
    history   = st.session_state.get("_answer_history", [])

    tab1, tab2, tab3, tab4 = st.tabs(
        ["📚 오늘의 학습", "📈 자산 성장", "🏅 뱃지 & 성취", "💳 금융상품 안내"]
    )

    with tab1:
        _tab_learning(gs, concepts, history, badge_engine)

    with tab2:
        _tab_assets(gs, history)

    with tab3:
        _tab_badges(gs, badge_engine)

    with tab4:
        _tab_products(gs, concepts, scenario_generator)
