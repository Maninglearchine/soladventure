import os
import streamlit.components.v1 as components

_FRONTEND = os.path.join(os.path.dirname(os.path.abspath(__file__)), "frontend")
_game_map = components.declare_component("finquest_game_map", path=_FRONTEND)


def render_game_map(world_id, zones, completed_zones, player_start=(5, 6), key=None):
    """
    Returns {"action": "enter_zone", "zone_id": "..."} when the player
    walks into a zone and presses Enter / clicks the prompt button.
    Returns None at all other times.
    """
    return _game_map(
        world_id=world_id,
        zones=[{"id": z["id"], "name": z["name"], "emoji": z["emoji"]} for z in zones],
        completed_zones=list(completed_zones),
        ptx=player_start[0],
        pty=player_start[1],
        key=key,
        default=None,
        height=470,
    )
