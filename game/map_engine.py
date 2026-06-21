import plotly.graph_objects as go
import streamlit as st


WORLD_COLORS = {
    "dinosaur": "#22c55e",
    "space": "#6366f1",
    "magic": "#f59e0b",
    "ocean": "#0ea5e9",
}


class MapEngine:
    def __init__(self, world_data: dict, player_pos: tuple, completed_missions: list):
        self.world = world_data
        self.player_x, self.player_y = player_pos
        self.completed_missions = completed_missions
        self.color = WORLD_COLORS.get(world_data["id"], "#6366f1")
        self.zones = world_data["zones"]

    def _zone_mission_ids(self, zone_id: str) -> list:
        prefix_map = {
            "dinosaur": "dino",
            "space": "space",
            "magic": "magic",
            "ocean": "ocean",
        }
        prefix = prefix_map.get(self.world["id"], self.world["id"])
        return [m for m in self.completed_missions if f"{prefix}_{zone_id}" in m or zone_id in m]

    def _is_zone_complete(self, zone_id: str) -> bool:
        done = [m for m in self.completed_missions if zone_id in m]
        return len(done) >= 2

    def render(self, recommended_zone_id: str | None = None) -> go.Figure:
        fig = go.Figure()

        bg_color = "#f0fdf4"
        if self.world["id"] == "space":
            bg_color = "#f5f3ff"
        elif self.world["id"] == "magic":
            bg_color = "#fffbeb"
        elif self.world["id"] == "ocean":
            bg_color = "#f0f9ff"

        fig.update_layout(
            paper_bgcolor=bg_color,
            plot_bgcolor=bg_color,
            margin=dict(l=10, r=10, t=10, b=10),
            height=320,
            xaxis=dict(range=[-0.5, 2.5], showgrid=False, zeroline=False, showticklabels=False, fixedrange=True),
            yaxis=dict(range=[-0.6, 0.6], showgrid=False, zeroline=False, showticklabels=False, fixedrange=True),
        )

        for zone in self.zones:
            x, y = zone["x"], zone["y"]
            is_current = (x == self.player_x and y == self.player_y)
            is_complete = self._is_zone_complete(zone["id"])
            is_recommended = zone["id"] == recommended_zone_id and not is_current

            border_color = self.color if is_current else ("#f59e0b" if is_recommended else "#d1d5db")
            border_width = 4 if is_current else (3 if is_recommended else 1.5)
            fill_color = "rgba(255,251,235,0.95)" if is_recommended else "rgba(255,255,255,0.95)"

            fig.add_shape(
                type="rect",
                x0=x - 0.42, y0=y - 0.38,
                x1=x + 0.42, y1=y + 0.38,
                line=dict(color=border_color, width=border_width),
                fillcolor=fill_color,
                layer="below",
            )

            fig.add_annotation(
                x=x, y=y + 0.15,
                text=zone["emoji"],
                showarrow=False,
                font=dict(size=28),
            )

            label = f"<b>{zone['name']}</b>"
            if is_complete:
                label = "✅ " + label
            elif is_recommended:
                label = "⭐ 추천 " + label
            fig.add_annotation(
                x=x, y=y - 0.12,
                text=label,
                showarrow=False,
                font=dict(size=12, color="#1f2937"),
            )

            fig.add_annotation(
                x=x, y=y - 0.28,
                text=f"<i>{zone['concept']}</i>",
                showarrow=False,
                font=dict(size=10, color="#6b7280"),
            )

        fig.add_trace(go.Scatter(
            x=[self.player_x],
            y=[self.player_y + 0.42],
            mode="text",
            text=["🧭"],
            textfont=dict(size=22),
            showlegend=False,
            hoverinfo="skip",
        ))

        return fig

    def get_zone_at(self, x: int, y: int) -> dict | None:
        for zone in self.zones:
            if zone["x"] == x and zone["y"] == y:
                return zone
        return None

    def current_zone(self) -> dict | None:
        return self.get_zone_at(self.player_x, self.player_y)
