"""
Helpers for the Phaser 3 game component.
"""


def get_world_missions(all_missions: list, zones: list, age_group: str) -> list:
    """Return missions that belong to any zone in `zones`, filtered by age group."""
    zone_ids = {z["id"] for z in zones}
    result = []
    for m in all_missions:
        if m.get("zone_id") not in zone_ids:
            continue
        if m.get("age_group") in ("all", age_group):
            result.append(m)
    return result


def preload_quizzes(world: str, age_group: str, character_name: str) -> list:
    """
    Generate patrol/chaser/boss quizzes for the Phaser game in parallel.
    Returns a list of 3 quiz dicts with enemy_type and id attached.
    Caches nothing — caller is responsible for caching in session state.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from ai.quiz_generator import QuizGenerator

    order = [
        ("patrol", "easy"),
        ("chaser", "medium"),
        ("boss",   "hard"),
    ]

    def _gen_one(enemy_type: str, difficulty: str) -> dict:
        gen = QuizGenerator()
        quiz = gen.generate_quiz(
            world=world,
            difficulty=difficulty,
            age_group=age_group,
            character_name=character_name,
            enemy_type=enemy_type,
        )
        quiz["enemy_type"] = enemy_type
        quiz["difficulty"] = difficulty
        quiz["id"]         = f"{world}_npc_{enemy_type}"
        return quiz

    results = {}
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {
            pool.submit(_gen_one, et, diff): (et, diff)
            for et, diff in order
        }
        for fut in as_completed(futures):
            et, _ = futures[fut]
            results[et] = fut.result()

    return [results[et] for et, _ in order]
