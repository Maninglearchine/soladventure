import os
import streamlit.components.v1 as components

_FRONTEND = os.path.join(os.path.dirname(os.path.abspath(__file__)), "frontend")
_phaser_game = components.declare_component("finquest_phaser_game", path=_FRONTEND)


def render_phaser_game(world, character_name, age_group, coins, level,
                       completed_missions, missions, quizzes=None, key=None,
                       battle_test=False):
    """
    Renders the Phaser 3 game.
    Returns a dict on QUIZ_RESULT, WORLD_CLEAR, or GAME_OVER events; None otherwise.
    """
    return _phaser_game(
        world=world,
        character_name=character_name,
        age_group=age_group,
        coins=int(coins),
        level=int(level),
        completed_missions=list(completed_missions),
        missions=missions,
        quizzes=quizzes or [],
        battle_test=bool(battle_test),
        key=key,
        default=None,
        height=540,
    )
