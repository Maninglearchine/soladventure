from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

WORLD_COLORS = {
    "dinosaur": "#22c55e",
    "space": "#6366f1",
    "magic": "#f59e0b",
    "ocean": "#0ea5e9",
}

_RADAR_CONCEPTS = ["저축", "투자", "용돈", "이자", "분산", "목표설정"]

_CONCEPT_MAP: dict[str, str] = {
    "저축": "저축",
    "목표 설정": "목표설정",
    "교환·거래": "용돈",
    "투자": "투자",
    "리스크": "투자",
    "분산 투자": "분산",
    "예산": "용돈",
    "필요 vs 욕구": "용돈",
    "충동 구매": "용돈",
    "이자": "이자",
    "복리": "이자",
    "장기 저축": "저축",
}


class PortfolioChart:

    # ── Coin history ─────────────────────────────────────────────────────────

    def render_coin_history(self, coin_log: list, world_id: str = "ocean") -> go.Figure:
        color = WORLD_COLORS.get(world_id, "#6366f1")

        if not coin_log:
            fig = go.Figure()
            fig.add_annotation(
                text="아직 미션을 완료하지 않았어요!",
                xref="paper", yref="paper", x=0.5, y=0.5,
                showarrow=False, font=dict(size=16, color="#9ca3af"),
            )
            fig.update_layout(height=250, paper_bgcolor="#f9fafb", plot_bgcolor="#f9fafb",
                              margin=dict(l=10, r=10, t=30, b=10))
            return fig

        xs = list(range(1, len(coin_log) + 1))
        ys = [e["total"] for e in coin_log]
        labels = [e.get("label", f"미션 {i+1}") for i, e in enumerate(coin_log)]
        deltas = [e["delta"] for e in coin_log]
        hover = [
            f"<b>{labels[i]}</b><br>코인 변화: {'+' if deltas[i]>=0 else ''}{deltas[i]}<br>누적: {ys[i]}코인"
            for i in range(len(coin_log))
        ]

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=xs, y=ys,
            mode="lines+markers",
            line=dict(color=color, width=3),
            marker=dict(size=10, color=color,
                        line=dict(color="white", width=2)),
            hovertext=hover,
            hoverinfo="text",
            fill="tozeroy",
            fillcolor=f"rgba{tuple(int(color.lstrip('#')[i:i+2], 16) for i in (0,2,4)) + (0.12,)}",
        ))
        fig.update_layout(
            height=260,
            margin=dict(l=10, r=10, t=30, b=10),
            xaxis=dict(title="미션 순서", showgrid=False, fixedrange=True),
            yaxis=dict(title="누적 코인 🪙", showgrid=True, gridcolor="#f3f4f6"),
            paper_bgcolor="white",
            plot_bgcolor="white",
            hovermode="closest",
        )
        return fig

    # ── Concept radar ─────────────────────────────────────────────────────────

    def build_concept_scores(self, answer_history: list) -> dict:
        totals: dict[str, list] = {c: [] for c in _RADAR_CONCEPTS}
        for entry in answer_history:
            radar_key = _CONCEPT_MAP.get(entry.get("concept", ""), None)
            if radar_key:
                totals[radar_key].append(1 if entry["correct"] else 0)
        return {
            c: (sum(v) / len(v) * 100 if v else 0)
            for c, v in totals.items()
        }

    def render_concept_radar(
        self, concept_scores: dict, world_id: str = "ocean"
    ) -> go.Figure:
        color = WORLD_COLORS.get(world_id, "#6366f1")
        concepts = _RADAR_CONCEPTS
        values = [concept_scores.get(c, 0) for c in concepts]
        values_closed = values + [values[0]]
        concepts_closed = concepts + [concepts[0]]

        fig = go.Figure(go.Scatterpolar(
            r=values_closed,
            theta=concepts_closed,
            fill="toself",
            fillcolor=f"rgba{tuple(int(color.lstrip('#')[i:i+2], 16) for i in (0,2,4)) + (0.25,)}",
            line=dict(color=color, width=2),
            marker=dict(size=6, color=color),
            hovertemplate="%{theta}: %{r:.0f}점<extra></extra>",
        ))
        fig.update_layout(
            polar=dict(
                radialaxis=dict(visible=True, range=[0, 100], showticklabels=True,
                                tickfont=dict(size=9), gridcolor="#e5e7eb"),
                angularaxis=dict(tickfont=dict(size=12)),
            ),
            showlegend=False,
            height=320,
            margin=dict(l=40, r=40, t=20, b=20),
            paper_bgcolor="white",
        )
        return fig

    # ── Savings growth ────────────────────────────────────────────────────────

    def render_savings_growth(
        self, initial: int = 1000, rate: float = 5.0, years: int = 30,
        world_id: str = "ocean",
    ) -> go.Figure:
        color = WORLD_COLORS.get(world_id, "#0ea5e9")
        checkpoints = [y for y in [5, 10, 15, 20, 25, 30] if y <= years]
        if years not in checkpoints:
            checkpoints.append(years)

        simple_values = [initial + initial * (rate / 100) * y for y in checkpoints]
        compound_values = [initial * ((1 + rate / 100) ** y) for y in checkpoints]
        labels = [f"{y}년" for y in checkpoints]

        r = tuple(int(color.lstrip('#')[i:i+2], 16) for i in (0, 2, 4))

        fig = go.Figure()
        fig.add_trace(go.Bar(
            name="단순 이자",
            x=labels, y=simple_values,
            marker_color=f"rgba{r + (0.4,)}",
            hovertemplate="%{x}: %{y:,.0f}코인<extra>단순이자</extra>",
        ))
        fig.add_trace(go.Bar(
            name="복리",
            x=labels, y=compound_values,
            marker_color=color,
            hovertemplate="%{x}: %{y:,.0f}코인<extra>복리</extra>",
        ))

        final_compound = compound_values[-1]
        final_simple = simple_values[-1]
        fig.add_annotation(
            x=labels[-1], y=final_compound,
            text=f"복리: {final_compound:,.0f}코인!",
            showarrow=True, arrowhead=2, arrowcolor=color,
            font=dict(size=11, color=color, family="bold"),
            bgcolor="white", bordercolor=color, borderwidth=1,
        )

        fig.update_layout(
            barmode="group",
            height=320,
            margin=dict(l=10, r=10, t=30, b=10),
            xaxis=dict(title="기간"),
            yaxis=dict(title="코인", showgrid=True, gridcolor="#f3f4f6"),
            paper_bgcolor="white",
            plot_bgcolor="white",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            title=dict(
                text=f"💡 {initial:,}코인을 연 {rate}% 이자율로 저축하면?",
                font=dict(size=14), x=0.5,
            ),
        )
        return fig

    # ── Badge progress ────────────────────────────────────────────────────────

    def render_badge_progress(self, badge_engine, game_state):
        from game.badge_engine import BADGES

        st.markdown("#### 🏅 뱃지 현황")
        earned_ids = set(game_state.badges)
        cols = st.columns(4)

        for i, badge in enumerate(BADGES):
            pct = badge_engine.badge_progress_pct(badge, game_state)
            earned = badge["id"] in earned_ids

            with cols[i % 4]:
                if earned:
                    st.markdown(
                        f"""
                        <div style="
                            background:linear-gradient(135deg,#fef3c7,#fde68a);
                            border:2px solid #f59e0b; border-radius:12px;
                            padding:10px; text-align:center; margin-bottom:8px;
                        ">
                            <div style="font-size:1.8rem;">{badge['emoji']}</div>
                            <div style="font-size:0.78rem; font-weight:700;
                                        color:#92400e; margin-top:4px;">
                                {badge['name']}
                            </div>
                            <div style="font-size:0.68rem; color:#78350f;">획득 ✅</div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
                else:
                    grey_emoji = "⬜"
                    st.markdown(
                        f"""
                        <div style="
                            background:#f9fafb; border:2px dashed #d1d5db;
                            border-radius:12px; padding:10px; text-align:center;
                            margin-bottom:8px;
                        ">
                            <div style="font-size:1.8rem; filter:grayscale(100%);">
                                {badge['emoji']}
                            </div>
                            <div style="font-size:0.78rem; font-weight:600;
                                        color:#6b7280; margin-top:4px;">
                                {badge['name']}
                            </div>
                            <div style="font-size:0.68rem; color:#9ca3af;">
                                {pct:.0%}
                            </div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
                    st.progress(pct)

        earned_count = len(earned_ids)
        total = len(BADGES)
        st.markdown(f"**전체 달성률: {earned_count}/{total}**")
        st.progress(earned_count / total)
