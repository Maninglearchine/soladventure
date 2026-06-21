import streamlit as st


def show_level_up(new_level: int):
    st.balloons()
    unlock_msg = " 새로운 세계가 열렸어요! 🌍" if new_level == 3 else ""
    st.success(
        f"🎉 **레벨 {new_level} 달성!** 탐험가로서 한 단계 성장했어요!{unlock_msg}",
        icon="⬆️",
    )


def show_badge_earned(badge: dict):
    st.toast(f"{badge['emoji']} **{badge['name']}** 뱃지 획득!", icon="🏅")
    st.success(
        f"### 🏅 새 뱃지 획득!\n"
        f"**{badge['emoji']} {badge['name']}** — {badge['desc']}",
        icon="✨",
    )


def show_coin_earned(amount: int):
    if amount > 0:
        st.toast(f"💰 +{amount} 코인!", icon="✨")
    elif amount < 0:
        st.toast(f"😅 {amount} 코인… 다음엔 더 잘할 수 있어요!", icon="💪")


def show_world_complete(world_name: str, next_world: str | None = None):
    st.balloons()
    msg = f"🎊 **{world_name} 세계 완료!** 모든 미션을 클리어했어요!"
    if next_world:
        msg += f"\n\n✨ **{next_world}** 세계의 잠금이 해제됐어요!"
    st.success(msg, icon="🌟")


def show_mission_streak(count: int):
    if count in (3, 5, 10):
        st.toast(f"🔥 연속 {count}번 도전! 대단한 탐험가예요!", icon="🔥")
