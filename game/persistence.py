"""
세션 간 게임 진행 데이터 저장/복원.

동작 방식:
  - URL query param 'sid'에 세션 ID를 저장한다.
  - 브라우저를 새로고침해도 URL에 sid가 남아 있어 같은 저장 파일을 불러온다.
  - 저장 위치: tempfile.gettempdir()/finquest_saves/{sid}.json
    (로컬 실행 기준 충분; 클라우드 배포 시 DB로 교체 가능)
"""

from __future__ import annotations

import json
import os
import tempfile

import streamlit as st

_SAVE_DIR = os.path.join(tempfile.gettempdir(), "finquest_saves")
os.makedirs(_SAVE_DIR, exist_ok=True)

_SAVE_FIELDS = [
    "character_name", "character_color", "age_group", "world",
    "coins", "level", "completed_missions", "badges", "coin_log",
    "page",
]


def _sid() -> str:
    """URL query param에서 세션 ID를 읽거나, 없으면 새로 생성해 URL에 기록한다."""
    sid = st.query_params.get("sid", "")
    if not sid:
        import uuid
        sid = uuid.uuid4().hex[:12]
        st.query_params["sid"] = sid
    return sid


def _save_path(sid: str) -> str:
    return os.path.join(_SAVE_DIR, f"{sid}.json")


# ── Public API ────────────────────────────────────────────────────────────────

def try_restore() -> bool:
    """앱 첫 실행(fresh session) 때 호출.
    URL에 sid가 있고 저장 파일이 존재하면 session_state에 복원한다.
    Returns True if restored, False otherwise.
    """
    # rerun 중에는 session_state가 살아 있으므로 중복 복원 방지
    if st.session_state.get("_persistence_loaded"):
        return False

    st.session_state["_persistence_loaded"] = True

    sid = st.query_params.get("sid", "")
    if not sid:
        return False

    path = _save_path(sid)
    if not os.path.exists(path):
        return False

    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        for k, v in data.items():
            st.session_state[k] = v
        return True
    except Exception:
        return False


def save_progress(gs) -> None:
    """게임 상태를 디스크에 저장한다. _post_mission_checks 등 주요 이벤트 후 호출."""
    try:
        sid = _sid()
        data = {f: getattr(gs, f) for f in _SAVE_FIELDS}
        with open(_save_path(sid), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        st.session_state["_last_saved"] = True
    except Exception:
        pass


def delete_save() -> None:
    """저장 파일을 삭제한다 (게임 리셋 시 호출)."""
    try:
        sid = st.query_params.get("sid", "")
        if sid:
            path = _save_path(sid)
            if os.path.exists(path):
                os.remove(path)
        st.session_state.pop("_last_saved", None)
        st.session_state.pop("sid", None)
    except Exception:
        pass
