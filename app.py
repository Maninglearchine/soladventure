import base64
import json
import os
import threading
import streamlit as st

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from game.state import GameState
from game.badge_engine import BadgeEngine
from game.phaser_builder import get_world_missions, preload_quizzes
from components.phaser_game import render_phaser_game
from ui.components import (
    render_header,
    render_concept_card,
    render_mission_result,
    render_badge,
    render_coin_animation,
    render_world_card,
)
from ui.animations import show_level_up, show_badge_earned, show_coin_earned

st.set_page_config(
    page_title="신한 쏠어드벤쳐 — 어린이 금융 탐험",
    page_icon="⭐",
    layout="centered",
    initial_sidebar_state="collapsed",
)

BASE = os.path.dirname(__file__)

_PROGRESS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "progress.json")

_PERSIST_MISSION_PREFIXES = ("world_clear_", "stage2_clear")

def _save_progress(gs):
    # NPC 퀴즈 ID(예: space_npc_boss)는 저장 제외 — 저장하면 재시작 후 보스가 스폰 안 됨
    missions_to_save = [
        m for m in gs.completed_missions
        if m.startswith("world_clear_") or m == "stage2_clear"
    ]
    data = {
        "completed_missions": missions_to_save,
        "badges": list(gs.badges),
        "coins": gs.coins,
    }
    try:
        with open(_PROGRESS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f)
    except Exception:
        pass

def _load_progress(gs):
    if not os.path.exists(_PROGRESS_FILE):
        return
    try:
        with open(_PROGRESS_FILE, encoding="utf-8") as f:
            data = json.load(f)
        for mid in data.get("completed_missions", []):
            if mid not in gs.completed_missions:
                gs.complete_mission(mid)
        for bid in data.get("badges", []):
            if bid not in gs.badges:
                gs.badges = gs.badges + [bid]
        if data.get("coins", 0) > gs.coins:
            gs.coins = data["coins"]
    except Exception:
        pass


WORLD_COLORS = {
    "dinosaur": "#22c55e",
    "space": "#6366f1",
    "magic": "#f59e0b",
    "ocean": "#0ea5e9",
}

SHINHAN_BLUE  = "#003082"
SHINHAN_BLUE2 = "#0057C2"


# ── Data & resource loaders ───────────────────────────────────────────────────

@st.cache_data
def load_worlds():
    with open(os.path.join(BASE, "data", "worlds.json"), encoding="utf-8") as f:
        return json.load(f)["worlds"]


@st.cache_data
def load_missions():
    with open(os.path.join(BASE, "data", "missions.json"), encoding="utf-8") as f:
        return json.load(f)["missions"]


@st.cache_resource
def get_rag_engine():
    from ai.rag_engine import RAGEngine
    return RAGEngine()


# ── Helpers ───────────────────────────────────────────────────────────────────

def get_world(worlds: list, world_id: str) -> dict | None:
    return next((w for w in worlds if w["id"] == world_id), None)


def get_zone_missions(missions: list, zone_id: str, age_group: str) -> list:
    filtered = [m for m in missions if m["zone_id"] == zone_id]
    age_filtered = [m for m in filtered if m["age_group"] in ("all", age_group)]
    return age_filtered if age_filtered else filtered


def has_api_key() -> bool:
    return bool(
        st.session_state.get("openai_api_key") or os.environ.get("OPENAI_API_KEY")
    )


def get_generator():
    from ai.scenario_generator import ScenarioGenerator
    return ScenarioGenerator(get_rag_engine())


def get_recommender():
    from ai.recommender import MissionRecommender
    return MissionRecommender()


def _total_completed() -> int:
    dynamic = sum(
        1 for k, v in st.session_state.items()
        if isinstance(k, str) and k.startswith("dynamic_done_") and v
    )
    return len(st.session_state.get("completed_missions", [])) + dynamic


# ── CSS ───────────────────────────────────────────────────────────────────────

def inject_css(world_id: str = "space"):
    color = WORLD_COLORS.get(world_id, "#6366f1")
    r, g, b = tuple(int(color.lstrip("#")[i:i+2], 16) for i in (0, 2, 4))
    st.markdown(
        f"""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Nunito:wght@400;600;700;800;900&display=swap');

        /* ── Animations ── */
        @keyframes floatY   {{ 0%,100%{{transform:translateY(0)}} 50%{{transform:translateY(-12px)}} }}
        @keyframes fadeUp   {{ from{{opacity:0;transform:translateY(28px)}} to{{opacity:1;transform:translateY(0)}} }}
        @keyframes popIn    {{ from{{opacity:0;transform:scale(.82)}} to{{opacity:1;transform:scale(1)}} }}
        @keyframes bounce   {{ 0%,100%{{transform:translateY(0) scale(1)}} 40%{{transform:translateY(-16px) scale(1.05)}} 60%{{transform:translateY(-6px) scale(1.02)}} }}
        @keyframes wiggle   {{ 0%,100%{{transform:rotate(0deg)}} 25%{{transform:rotate(-6deg)}} 75%{{transform:rotate(6deg)}} }}
        @keyframes sparkle  {{ 0%,100%{{opacity:.6;transform:scale(1)}} 50%{{opacity:1;transform:scale(1.3)}} }}
        @keyframes shimmer  {{ 0%{{background-position:200% center}} 100%{{background-position:-200% center}} }}
        @keyframes starFloat {{ 0%{{transform:translateY(0) rotate(0deg);opacity:.7}} 50%{{transform:translateY(-20px) rotate(180deg);opacity:1}} 100%{{transform:translateY(0) rotate(360deg);opacity:.7}} }}
        @keyframes pulse    {{ 0%,100%{{box-shadow:0 0 0 0 rgba({r},{g},{b},.5)}} 70%{{box-shadow:0 0 0 14px transparent}} }}

        header[data-testid="stHeader"], footer {{ display:none !important; }}
        #MainMenu {{ visibility:hidden !important; }}
        section[data-testid="stSidebar"] {{ display:none !important; }}

        /* ── Background — Vibrant Shinhan Blue ── */
        .stApp, section[data-testid="stMain"], section[data-testid="stMain"] > div, .main > div {{
            background: linear-gradient(160deg, #001F8C 0%, #0044CC 28%, #0068FF 58%, #1E8FFF 80%, #55B8FF 100%) !important;
            font-family: 'Nunito', 'Apple SD Gothic Neo', sans-serif !important;
        }}
        /* Decorative orbs */
        .stApp::before {{
            content:''; position:fixed; top:-160px; right:-100px;
            width:520px; height:520px; border-radius:50%;
            background:radial-gradient(circle, rgba(255,100,100,.2) 0%, transparent 65%);
            pointer-events:none; z-index:0;
        }}
        .stApp::after {{
            content:''; position:fixed; bottom:-120px; left:-80px;
            width:420px; height:420px; border-radius:50%;
            background:radial-gradient(circle, rgba(255,210,0,.18) 0%, transparent 65%);
            pointer-events:none; z-index:0;
        }}
        .block-container {{
            background: transparent !important;
            max-width: 920px !important;
            padding-top: 1.2rem !important;
        }}

        /* ── Buttons ── */
        .stButton > button {{
            border-radius: 20px !important;
            font-weight: 800 !important;
            font-size: .95rem !important;
            letter-spacing: .2px !important;
            transition: all .25s cubic-bezier(.34,1.56,.64,1) !important;
            color: white !important;
            background: rgba(255,255,255,.15) !important;
            backdrop-filter: blur(16px) !important;
            -webkit-backdrop-filter: blur(16px) !important;
            border: 2px solid rgba(255,255,255,.3) !important;
            padding: 12px 28px !important;
            box-shadow: 0 4px 20px rgba(0,0,0,.18), inset 0 1px 0 rgba(255,255,255,.25) !important;
        }}
        .stButton > button:hover {{
            background: rgba(255,255,255,.25) !important;
            border-color: rgba(255,255,255,.5) !important;
            color: white !important;
            transform: translateY(-3px) scale(1.04) !important;
            box-shadow: 0 12px 32px rgba(0,0,0,.25), inset 0 1px 0 rgba(255,255,255,.3) !important;
        }}
        .stButton > button:active {{
            transform: translateY(0) scale(.98) !important;
        }}
        .stButton > button[kind="primary"] {{
            background: linear-gradient(135deg, #FF6B6B 0%, #FF8E53 100%) !important;
            color: white !important;
            border: none !important;
            box-shadow: 0 6px 24px rgba(255,107,107,.55), inset 0 1px 0 rgba(255,255,255,.25) !important;
        }}
        .stButton > button[kind="primary"]:hover {{
            background: linear-gradient(135deg, #FF5252 0%, #FF7043 100%) !important;
            box-shadow: 0 10px 36px rgba(255,107,107,.7) !important;
            transform: translateY(-4px) scale(1.04) !important;
        }}

        /* ── Glass card ── */
        .glass-card {{
            background: rgba(255,255,255,.1);
            backdrop-filter: blur(28px);
            -webkit-backdrop-filter: blur(28px);
            border: 2px solid rgba(255,255,255,.22);
            border-top: 3px solid rgba(255,255,255,.45);
            border-radius: 28px;
            box-shadow: 0 12px 40px rgba(0,0,0,.2), inset 0 1px 0 rgba(255,255,255,.15);
        }}

        /* ── Progress bar ── */
        div[data-testid="stProgress"] > div {{
            background: linear-gradient(90deg, #FF6B6B, {color}, #FFD60A);
            border-radius: 100px;
        }}

        /* ── Text ── */
        div[data-testid="stMarkdownContainer"] p,
        div[data-testid="stMarkdownContainer"] h1,
        div[data-testid="stMarkdownContainer"] h2,
        div[data-testid="stMarkdownContainer"] h3,
        div[data-testid="stMarkdownContainer"] h4,
        div[data-testid="stMarkdownContainer"] li,
        div[data-testid="stMarkdownContainer"] span,
        div[data-testid="stMarkdownContainer"] a,
        div[data-testid="stCaptionContainer"] p,
        div[data-testid="stText"] p,
        label[data-testid="stWidgetLabel"] p {{ color: white !important; }}
        [data-testid="stButton"] p,
        [data-testid="stButton"] span,
        [data-testid="stButton"] [data-testid="stMarkdownContainer"] p,
        [data-testid="stButton"] [data-testid="stMarkdownContainer"] span {{ color: white !important; }}
        div[data-testid="stSpinner"] p, div[data-testid="stSpinner"] span {{ color: white !important; }}
        hr {{ border-color: rgba(255,255,255,.15) !important; margin: 1.2rem 0 !important; }}

        /* ── Tooltip ── */
        [data-testid="tooltipContent"],
        [data-testid="tooltipContent"] p,
        [data-testid="tooltipContent"] span,
        div[role="tooltip"],
        div[role="tooltip"] p,
        div[role="tooltip"] span {{ color: #0d1b3e !important; background: white; }}

        /* ── Toast 알림 — 흰 배경에 검은 글씨 ── */
        [data-testid*="Toast"] *,
        [data-testid*="toast"] *,
        [class*="Toast"] *,
        [class*="toast"] * {{ color: #111111 !important; }}
        [data-testid*="Toast"],
        [data-testid*="toast"],
        [class*="Toast"],
        [class*="toast"] {{ color: #111111 !important; }}

        /* ── Top nav — logo button ── */
        div:has(#top-nav-sentinel) ~ [data-testid="stHorizontalBlock"] > div:first-child [data-testid="stButton"] {{
            margin-top: 0 !important; z-index: auto !important;
        }}
        div:has(#top-nav-sentinel) ~ [data-testid="stHorizontalBlock"] > div:first-child [data-testid="stButton"] button {{
            display: inline-flex !important; align-items: center !important; gap: 8px !important;
            background: white !important;
            border: none !important;
            border-radius: 100px !important; padding: 7px 18px 7px 7px !important;
            color: #003082 !important; font-weight: 900 !important; font-size: 13px !important;
            box-shadow: 0 4px 16px rgba(0,0,0,.18) !important;
        }}
        div:has(#top-nav-sentinel) ~ [data-testid="stHorizontalBlock"] > div:first-child [data-testid="stButton"] button::before {{
            content: "신";
            display: inline-flex; align-items: center; justify-content: center;
            width: 28px; height: 28px; min-width: 28px;
            background: linear-gradient(135deg, #0044CC, #0068FF); border-radius: 50%;
            font-size: 12px; font-weight: 900; color: white; flex-shrink: 0;
        }}
        div:has(#top-nav-sentinel) ~ [data-testid="stHorizontalBlock"] > div:first-child [data-testid="stButton"] button:hover {{
            transform: translateY(-2px) !important; box-shadow: 0 8px 24px rgba(0,0,0,.25) !important;
        }}
        div:has(#top-nav-sentinel) ~ [data-testid="stHorizontalBlock"] > div:first-child [data-testid="stButton"] p,
        div:has(#top-nav-sentinel) ~ [data-testid="stHorizontalBlock"] > div:first-child [data-testid="stButton"] span {{
            color: #003082 !important;
        }}
        /* ── Nav icon buttons ── */
        div:has(#top-nav-sentinel) button[data-testid="stBaseButton-secondary"] {{
            background: rgba(255,255,255,.15) !important;
            backdrop-filter: blur(12px) !important;
            border: 2px solid rgba(255,255,255,.28) !important;
            border-radius: 16px !important;
            color: white !important; font-size: 1.1rem !important;
            box-shadow: 0 2px 10px rgba(0,0,0,.12) !important;
        }}
        div:has(#top-nav-sentinel) button[data-testid="stBaseButton-secondary"]:hover {{
            background: rgba(255,255,255,.25) !important;
            transform: translateY(-2px) scale(1.08) !important;
            box-shadow: 0 6px 20px rgba(0,0,0,.2) !important;
        }}

        /* ── Input fields ── */
        .stTextInput input, .stSelectbox select {{
            background: rgba(255,255,255,.12) !important;
            border: 2px solid rgba(255,255,255,.28) !important;
            border-radius: 16px !important;
            color: white !important;
            font-size: 1rem !important;
        }}
        .stTextInput input::placeholder {{ color: rgba(255,255,255,.5) !important; }}

        /* ── Tabs ── */
        button[data-baseweb="tab"] {{
            background: rgba(255,255,255,.1) !important;
            border-radius: 16px 16px 0 0 !important;
            color: rgba(255,255,255,.7) !important;
            font-weight: 700 !important;
            border: none !important;
            font-size: .92rem !important;
        }}
        button[data-baseweb="tab"][aria-selected="true"] {{
            background: rgba(255,255,255,.22) !important;
            color: white !important;
            border-bottom: 3px solid #FFD60A !important;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )
    _inject_bgm()


# ── Persistent BGM ────────────────────────────────────────────────────────────

def _inject_bgm():
    """Inject BGM1. Creates the element once; resumes it when returning from game."""
    import streamlit.components.v1 as components
    components.html(
        """
        <script>
        (function() {
            var doc = window.parent.document;
            var existing = doc.getElementById('app-bgm1');
            if (existing) {
                if (existing.paused) existing.play().catch(function(){});
                return;
            }
            var a = doc.createElement('audio');
            a.id = 'app-bgm1';
            a.src = '/app/static/bgm.wav';
            a.loop = true;
            a.volume = 0.35;
            doc.body.appendChild(a);
            a.play().catch(function() {
                doc.addEventListener('click', function resume() {
                    a.play();
                    doc.removeEventListener('click', resume);
                }, { once: true });
            });
        })();
        </script>
        """,
        height=0,
    )


# ── Sidebar ───────────────────────────────────────────────────────────────────

def render_sidebar(gs: GameState, badge_engine: BadgeEngine, worlds: list):
    pass  # Sidebar hidden — navigation is via top nav bar


# ── Post-mission processing ───────────────────────────────────────────────────

def _post_mission_checks(gs: GameState, badge_engine: BadgeEngine):
    """Call after a mission is completed to handle level-up and badges."""
    new_level, leveled_up = gs.recalculate_level()
    if leveled_up:
        show_level_up(new_level)

    new_badges = badge_engine.check_and_award(gs)
    for badge in new_badges:
        show_badge_earned(badge)

    # 미션 완료 시 자동 저장 (새로고침 후 복원 가능)
    try:
        from game.persistence import save_progress
        save_progress(gs)
    except Exception:
        pass


# ── Intro constants ───────────────────────────────────────────────────────────

CHARACTERS = [
    {"name": "쏠쏠이", "emoji": "⭐", "color": "#ffd700", "desc": "밝고 씩씩한 우주 탐험가", "image": "assets/characters/solsol.png"},
    {"name": "몰리",   "emoji": "🌸", "color": "#f9a8d4", "desc": "따뜻하고 영리한 여행자",        "image": "assets/characters/molly.png"},
    {"name": "쏠리",   "emoji": "🌊", "color": "#7dd3fc", "desc": "용감하고 호기심 많은 모험가", "image": "assets/characters/rino.png"},
]


def _char_icon_html(ch: dict, size: int = 80) -> str:
    size = ch.get("image_size", size)
    img_path = ch.get("image")
    if img_path:
        full = os.path.join(BASE, img_path)
        if os.path.exists(full):
            with open(full, "rb") as f:
                b64 = base64.b64encode(f.read()).decode()
            ext = img_path.rsplit(".", 1)[-1].lower()
            mime = "jpeg" if ext == "jpg" else ext
            return (
                f'<img src="data:image/{mime};base64,{b64}"'
                f' style="width:{size}px;height:{size}px;object-fit:contain;'
                f'margin-bottom:10px;border-radius:16px;">'
            )
    return f'<div style="font-size:3.4rem;margin-bottom:10px;">{ch["emoji"]}</div>'

AGE_GROUPS = [
    {"label": "7~9살",     "value": "young",  "emoji": "👶", "desc": "쉬운 용돈·소비 문제"},
    {"label": "10~12살",   "value": "middle", "emoji": "🧒", "desc": "저축·소비·필요와 욕구"},
    {"label": "13살 이상", "value": "senior", "emoji": "🧑", "desc": "예산·이자·금융 선택"},
]

# ── Background preload cache ───────────────────────────────────────────────────
_BG_CACHE: dict = {}       # key → result (module-level, survives reruns)
_BG_LOCK = threading.Lock()
_BG_RUNNING: set = set()   # keys currently being fetched


def _bg_run(key: str, fn, *args):
    """Generic background worker: skip if already running/cached."""
    with _BG_LOCK:
        if key in _BG_CACHE or key in _BG_RUNNING:
            return
        _BG_RUNNING.add(key)
    try:
        result = fn(*args)
        with _BG_LOCK:
            _BG_CACHE[key] = result
    except Exception:
        with _BG_LOCK:
            _BG_CACHE[key] = []   # empty sentinel so we don't retry forever
    finally:
        with _BG_LOCK:
            _BG_RUNNING.discard(key)


def _bg_fetch_news(age_group: str):
    from ai.news_crawler import get_kids_news
    return get_kids_news(n=5, age_group=age_group, character_name="쏠쏠이")


def _bg_fetch_quizzes(world: str, age_group: str, character_name: str):
    return preload_quizzes(world, age_group, character_name)


def kick_preloads(gs) -> None:
    """백그라운드 프리로드. 매 rerun마다 호출해도 안전 (중복 실행 없음)."""
    age  = getattr(gs, "age_group",    None) or "all"
    char = getattr(gs, "character_name", "")
    world = getattr(gs, "world", None)
    intro_step = st.session_state.get("intro_step", 0)

    # 뉴스: 앱 시작 즉시
    news_key = "_kids_news_cache"
    with _BG_LOCK:
        news_idle = news_key not in _BG_CACHE and news_key not in _BG_RUNNING
    if news_idle:
        threading.Thread(
            target=_bg_run, args=(news_key, _bg_fetch_news, age), daemon=True
        ).start()

    # 퀴즈: 나이 선택 완료(intro_step >= 2) 시점부터 3개 월드 전부 병렬 preload
    # → 월드 선택·finale 읽는 동안 이미 완료되도록
    if intro_step >= 2 or world:
        worlds_to_preload = [world] if world else ["space", "ocean", "magic"]
        for w in worlds_to_preload:
            quiz_key = f"_quizzes_{w}"
            with _BG_LOCK:
                quiz_idle = quiz_key not in _BG_CACHE and quiz_key not in _BG_RUNNING
            if quiz_idle:
                threading.Thread(
                    target=_bg_run,
                    args=(quiz_key, _bg_fetch_quizzes, w, age, char),
                    daemon=True,
                ).start()


CHAR_EVOLUTION = {
    "쏠쏠이": [
        {"emoji": "⭐",  "tier_name": "새싹 탐험가", "desc": "금융 여행을 막 시작했어요!"},
        {"emoji": "🌟",  "tier_name": "금융 전사",   "desc": "주식 지식이 쑥쑥 자라고 있어요!"},
        {"emoji": "💫",  "tier_name": "주식 마스터", "desc": "완벽한 금융 달인이 됐어요! 👑"},
    ],
    "몰리": [
        {"emoji": "🌸",  "tier_name": "새싹 탐험가", "desc": "금융 여행을 막 시작했어요!"},
        {"emoji": "🌺",  "tier_name": "금융 전사",   "desc": "주식 지식이 쑥쑥 자라고 있어요!"},
        {"emoji": "💎",  "tier_name": "주식 마스터", "desc": "완벽한 금융 달인이 됐어요! 👑"},
    ],
    "쏠리": [
        {"emoji": "🌊",  "tier_name": "새싹 탐험가", "desc": "금융 여행을 막 시작했어요!"},
        {"emoji": "🌈",  "tier_name": "금융 전사",   "desc": "주식 지식이 쑥쑥 자라고 있어요!"},
        {"emoji": "⚡",  "tier_name": "주식 마스터", "desc": "완벽한 금융 달인이 됐어요! 👑"},
    ],
}

WORLD_FINANCIAL_TIPS = {
    "space": [
        "주식은 회사의 아주 작은 조각을 사는 거예요!",
        "주식 가격은 오르기도 하고 내리기도 해요 — 길게 보는 게 포인트예요!",
        "여러 주식에 나눠 투자하는 '분산 투자'가 안전해요!",
    ],
    "dinosaur": [
        "저금은 미래를 위해 지금 돈을 모아두는 것이에요!",
        "용돈을 계획적으로 쓰면 더 많은 돈을 모을 수 있어요!",
        "작은 금액도 꾸준히 모으면 큰돈이 돼요!",
    ],
    "magic": [
        "예산을 세우면 돈을 더 현명하게 쓸 수 있어요!",
        "필요한 것과 갖고 싶은 것을 구분하는 게 중요해요!",
        "복리로 굴리면 시간이 지날수록 돈이 쑥쑥 늘어나요!",
    ],
    "ocean": [
        "보험은 갑작스러운 사고나 병을 대비하는 안전망이에요!",
        "빌린 돈(부채)은 꼭 갚아야 해요. 이자도 붙어요!",
        "세금은 우리가 함께 쓰는 도로·학교·병원을 만들어요!",
    ],
}

INTRO_WORLDS = [
    {
        "id": "space",  "emoji": "🚀",
        "name": "별빛 금융 은하",
        "villain": "블랙홀 먹깨비",
        "desc": "우주를 탐험하며 주식·투자의 비밀을 배우고 스타 쏠코인을 되찾아요!",
        "color": "#6366f1",
    },
    {
        "id": "ocean",  "emoji": "🐋",
        "name": "파도 저금섬",
        "villain": "낭비 문어",
        "desc": "맑은 바다 속에서 진주 쏠코인을 찾아요!",
        "color": "#0ea5e9",
    },
    {
        "id": "magic",  "emoji": "✨",
        "name": "용돈 마법왕국",
        "villain": "충동구매 마법사",
        "desc": "마법 숲과 성을 누비며 쏠코인을 구해요!",
        "color": "#a855f7",
    },
]


# ── Intro CSS ──────────────────────────────────────────────────────────────────

def _inject_intro_css():
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Nunito:wght@400;600;700;800;900&display=swap');

        header[data-testid="stHeader"], footer { display:none !important; }
        #MainMenu { visibility:hidden !important; }
        section[data-testid="stSidebar"] { display:none !important; }

        /* ── Background — Vibrant Shinhan Blue ── */
        .stApp, section[data-testid="stMain"], section[data-testid="stMain"] > div, .main > div {
            background: linear-gradient(160deg, #001F8C 0%, #0044CC 28%, #0068FF 58%, #1E8FFF 80%, #55B8FF 100%) !important;
            font-family: 'Nunito', 'Apple SD Gothic Neo', sans-serif !important;
        }
        .block-container { background:transparent !important; max-width:920px !important; padding-top:0 !important; }

        /* ── Decorative orbs ── */
        .stApp::before {
            content:''; position:fixed; top:-160px; right:-100px;
            width:520px; height:520px; border-radius:50%;
            background:radial-gradient(circle,rgba(255,100,100,.2) 0%,transparent 65%);
            pointer-events:none; z-index:0;
        }
        .stApp::after {
            content:''; position:fixed; bottom:-120px; left:-80px;
            width:420px; height:420px; border-radius:50%;
            background:radial-gradient(circle,rgba(255,210,0,.18) 0%,transparent 65%);
            pointer-events:none; z-index:0;
        }

        /* ── Animations ── */
        @keyframes floatY   { 0%,100%{transform:translateY(0)} 50%{transform:translateY(-14px)} }
        @keyframes fadeUp   { from{opacity:0;transform:translateY(30px)} to{opacity:1;transform:translateY(0)} }
        @keyframes fadeIn   { from{opacity:0} to{opacity:1} }
        @keyframes bounce   { 0%,100%{transform:translateY(0) scale(1)} 40%{transform:translateY(-20px) scale(1.06)} 60%{transform:translateY(-8px) scale(1.02)} }
        @keyframes popIn    { from{opacity:0;transform:scale(.78)} to{opacity:1;transform:scale(1)} }
        @keyframes wiggle   { 0%,100%{transform:rotate(0deg)} 25%{transform:rotate(-8deg)} 75%{transform:rotate(8deg)} }
        @keyframes glow     { 0%,100%{filter:drop-shadow(0 0 8px rgba(255,255,255,.3))} 50%{filter:drop-shadow(0 0 24px rgba(255,255,255,.8))} }
        @keyframes dotPulse { 0%,100%{transform:scale(1)} 50%{transform:scale(1.5)} }
        @keyframes sparkle  { 0%,100%{opacity:.5;transform:scale(.8) rotate(0deg)} 50%{opacity:1;transform:scale(1.2) rotate(180deg)} }
        @keyframes rainbow  { 0%{color:#FF6B6B} 20%{color:#FFD60A} 40%{color:#06D6A0} 60%{color:#5AB4FF} 80%{color:#845EF7} 100%{color:#FF6B6B} }

        /* ── Glass card ── */
        .fq-card {
            background: rgba(255,255,255,.1);
            backdrop-filter: blur(32px);
            -webkit-backdrop-filter: blur(32px);
            border: 2px solid rgba(255,255,255,.22);
            border-top: 3px solid rgba(255,255,255,.5);
            border-radius: 32px;
            padding: 36px 16px 28px;
            text-align: center;
            transition: all .32s cubic-bezier(.34,1.56,.64,1);
            margin-bottom: 8px;
            position: relative;
            overflow: hidden;
            box-shadow: 0 12px 40px rgba(0,0,0,.2), inset 0 1px 0 rgba(255,255,255,.18);
        }
        .fq-card::after {
            content: '';
            position: absolute; top: 0; left: 0; right: 0; height: 2px;
            background: linear-gradient(90deg, rgba(255,107,107,.6) 0%, rgba(255,214,10,.6) 50%, rgba(6,214,160,.6) 100%);
            border-radius: 32px 32px 0 0;
            opacity: 0;
            transition: opacity .3s;
        }
        .fq-card:hover {
            background: rgba(255,255,255,.18);
            border-color: rgba(255,255,255,.4);
            transform: translateY(-14px) scale(1.04);
            box-shadow: 0 36px 72px rgba(0,0,0,.3), inset 0 1px 0 rgba(255,255,255,.25);
        }
        .fq-card:hover::after { opacity: 1; }

        /* ── Colored card variants ── */
        .fq-card-coral  { border-top-color: rgba(255,107,107,.8) !important; }
        .fq-card-yellow { border-top-color: rgba(255,214,10,.8) !important; }
        .fq-card-green  { border-top-color: rgba(6,214,160,.8) !important; }
        .fq-card-purple { border-top-color: rgba(132,94,247,.8) !important; }

        /* ── Speech bubble ── */
        .fq-bubble {
            background: rgba(255,255,255,.1);
            backdrop-filter: blur(24px);
            -webkit-backdrop-filter: blur(24px);
            border: 2px solid rgba(255,255,255,.22);
            border-top: 2px solid rgba(255,255,255,.45);
            border-radius: 28px;
            padding: 24px 28px;
            margin: 18px auto 22px;
            max-width: 620px;
            text-align: left;
            animation: fadeUp .55s cubic-bezier(.34,1.56,.64,1);
            box-shadow: 0 14px 48px rgba(0,0,0,.2), inset 0 1px 0 rgba(255,255,255,.15);
        }

        /* ── Progress dots ── */
        .fq-dots { text-align:center; margin:10px 0 0; display:flex; align-items:center; justify-content:center; gap:8px; }
        .fq-dot  {
            display:inline-block; width:9px; height:9px; border-radius:50%;
            background:rgba(255,255,255,.25); transition:all .35s cubic-bezier(.34,1.56,.64,1);
        }
        .fq-dot.active {
            background: linear-gradient(90deg, #FFD60A, #FF6B6B);
            width: 28px; border-radius: 100px;
            box-shadow: 0 0 14px rgba(255,214,10,.6);
            animation: dotPulse 2s ease-in-out infinite;
        }

        /* ── Buttons ── */
        .stButton > button {
            border-radius: 20px !important;
            font-weight: 800 !important;
            font-size: .95rem !important;
            letter-spacing: .2px !important;
            transition: all .26s cubic-bezier(.34,1.56,.64,1) !important;
            color: white !important;
            background: rgba(255,255,255,.15) !important;
            backdrop-filter: blur(16px) !important;
            -webkit-backdrop-filter: blur(16px) !important;
            border: 2px solid rgba(255,255,255,.3) !important;
            padding: 12px 28px !important;
            box-shadow: 0 4px 20px rgba(0,0,0,.18), inset 0 1px 0 rgba(255,255,255,.25) !important;
        }
        .stButton > button:hover {
            background: rgba(255,255,255,.25) !important;
            border-color: rgba(255,255,255,.5) !important;
            color: white !important;
            transform: translateY(-3px) scale(1.05) !important;
            box-shadow: 0 12px 32px rgba(0,0,0,.25), inset 0 1px 0 rgba(255,255,255,.3) !important;
        }
        .stButton > button:active { transform: translateY(0) scale(.97) !important; }
        .stButton > button[kind="primary"] {
            background: linear-gradient(135deg, #FF6B6B 0%, #FF8E53 100%) !important;
            color: white !important;
            border: none !important;
            box-shadow: 0 6px 24px rgba(255,107,107,.55), inset 0 1px 0 rgba(255,255,255,.25) !important;
        }
        .stButton > button[kind="primary"]:hover {
            background: linear-gradient(135deg, #FF5252 0%, #FF7043 100%) !important;
            box-shadow: 0 10px 36px rgba(255,107,107,.7) !important;
            transform: translateY(-4px) scale(1.05) !important;
        }
        div[data-testid="stButton"] { margin-top:-2px !important; }

        /* ── Card overlay invisible button ── */
        div:has(#char-select-sentinel) ~ [data-testid="stHorizontalBlock"] [data-testid="stButton"],
        div:has(#age-select-sentinel)  ~ [data-testid="stHorizontalBlock"] [data-testid="stButton"] {
            margin-top: -230px !important; position: relative !important; z-index: 5 !important;
        }
        div:has(#char-select-sentinel) ~ [data-testid="stHorizontalBlock"] [data-testid="stButton"] button,
        div:has(#age-select-sentinel)  ~ [data-testid="stHorizontalBlock"] [data-testid="stButton"] button {
            min-height: 230px !important; width: 100% !important;
            opacity: 0.001 !important; cursor: pointer !important;
            background: transparent !important; border: none !important;
            box-shadow: none !important; border-radius: 32px !important;
            transform: none !important;
        }
        div:has(#char-select-sentinel) ~ [data-testid="stHorizontalBlock"] [data-testid="stButton"] button:hover,
        div:has(#age-select-sentinel)  ~ [data-testid="stHorizontalBlock"] [data-testid="stButton"] button:hover {
            transform: none !important; box-shadow: none !important; background: transparent !important;
        }
        div:has(#char-select-sentinel) ~ [data-testid="stHorizontalBlock"] [data-testid="stColumn"]:has([data-testid="stButton"] button:hover) .fq-card,
        div:has(#age-select-sentinel)  ~ [data-testid="stHorizontalBlock"] [data-testid="stColumn"]:has([data-testid="stButton"] button:hover) .fq-card {
            background: rgba(255,255,255,.2) !important;
            border-color: rgba(255,255,255,.45) !important;
            transform: translateY(-14px) scale(1.04) !important;
            box-shadow: 0 36px 72px rgba(0,0,0,.32) !important;
        }

        /* ── White text ── */
        div[data-testid="stMarkdownContainer"] p,
        div[data-testid="stMarkdownContainer"] h1,
        div[data-testid="stMarkdownContainer"] h2,
        div[data-testid="stMarkdownContainer"] h3,
        div[data-testid="stMarkdownContainer"] h4,
        div[data-testid="stMarkdownContainer"] li,
        div[data-testid="stMarkdownContainer"] span,
        div[data-testid="stMarkdownContainer"] a,
        div[data-testid="stCaptionContainer"] p,
        div[data-testid="stText"] p,
        label[data-testid="stWidgetLabel"] p { color: white !important; }
        [data-testid="stButton"] p,
        [data-testid="stButton"] span,
        [data-testid="stButton"] [data-testid="stMarkdownContainer"] p,
        [data-testid="stButton"] [data-testid="stMarkdownContainer"] span { color: white !important; }
        div[data-testid="stSpinner"] p, div[data-testid="stSpinner"] span { color: white !important; }
        hr { border-color: rgba(255,255,255,.15) !important; margin: 1.2rem 0 !important; }

        /* ── Logo button ── */
        div:has(#top-nav-sentinel) ~ [data-testid="stHorizontalBlock"] > div:first-child [data-testid="stButton"] {
            margin-top: 0 !important; z-index: auto !important;
        }
        div:has(#top-nav-sentinel) ~ [data-testid="stHorizontalBlock"] > div:first-child [data-testid="stButton"] button {
            display: inline-flex !important; align-items: center !important; gap: 8px !important;
            background: white !important; border: none !important;
            border-radius: 100px !important; padding: 7px 18px 7px 7px !important;
            color: #003082 !important; font-weight: 900 !important; font-size: 13px !important;
            box-shadow: 0 4px 16px rgba(0,0,0,.18) !important;
        }
        div:has(#top-nav-sentinel) ~ [data-testid="stHorizontalBlock"] > div:first-child [data-testid="stButton"] button::before {
            content: "신";
            display: inline-flex; align-items: center; justify-content: center;
            width: 28px; height: 28px; min-width: 28px;
            background: linear-gradient(135deg, #0044CC, #0068FF); border-radius: 50%;
            font-size: 12px; font-weight: 900; color: white; flex-shrink: 0;
        }
        div:has(#top-nav-sentinel) ~ [data-testid="stHorizontalBlock"] > div:first-child [data-testid="stButton"] button:hover {
            transform: translateY(-2px) !important; box-shadow: 0 8px 24px rgba(0,0,0,.25) !important;
        }
        div:has(#top-nav-sentinel) ~ [data-testid="stHorizontalBlock"] > div:first-child [data-testid="stButton"] p,
        div:has(#top-nav-sentinel) ~ [data-testid="stHorizontalBlock"] > div:first-child [data-testid="stButton"] span {
            color: #003082 !important;
        }
        /* ── Nav icon buttons ── */
        div:has(#top-nav-sentinel) button[data-testid="stBaseButton-secondary"] {
            background: rgba(255,255,255,.15) !important;
            backdrop-filter: blur(12px) !important;
            border: 2px solid rgba(255,255,255,.28) !important;
            border-radius: 16px !important;
            color: white !important; font-size: 1.05rem !important;
            box-shadow: 0 2px 10px rgba(0,0,0,.12) !important;
        }
        div:has(#top-nav-sentinel) button[data-testid="stBaseButton-secondary"]:hover {
            background: rgba(255,255,255,.25) !important;
            transform: translateY(-2px) scale(1.08) !important;
            box-shadow: 0 6px 20px rgba(0,0,0,.2) !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    _inject_bgm()


def _render_shinhan_logo_bar(step: int = 0):
    """Top logo strip shown on every onboarding screen."""
    dots_html = "".join(
        f'<span class="fq-dot{"  active" if i == step else ""}"></span>'
        for i in range(4)
    )
    st.markdown('<div id="top-nav-sentinel"></div>', unsafe_allow_html=True)
    col_logo, col_dots, col_report, col_battle = st.columns([2, 4, 2, 2])
    with col_logo:
        if st.button("🏠 처음으로 돌아가기", key=f"logo_home_{step}", use_container_width=False):
            st.session_state["intro_step"] = 0
            st.rerun()
    with col_dots:
        st.markdown(
            f'<div class="fq-dots" style="padding-top:12px;">{dots_html}</div>',
            unsafe_allow_html=True,
        )
    with col_report:
        if st.button("📊 결과 리포트", key=f"temp_report_{step}", use_container_width=True):
            st.session_state["page"] = "report"
            st.rerun()
    with col_battle:
        if st.button("⚔️ 배틀 테스트", key=f"temp_battle_{step}", use_container_width=True):
            st.session_state["battle_test_mode"] = True
            st.session_state["page"] = "map"
            st.rerun()
    st.markdown("<div style='margin-bottom:4px'></div>", unsafe_allow_html=True)


def _render_top_nav(gs: GameState):
    """Top navigation bar shown on game/news/report pages."""
    st.markdown('<div id="top-nav-sentinel"></div>', unsafe_allow_html=True)
    col_logo, col_w, col_a, col_s, col_p, col_btn = st.columns([3, 1, 1, 1, 1, 2])
    with col_logo:
        if st.button("🏠 처음으로 돌아가기", key="top_nav_home", use_container_width=False):
            gs.go_to("onboarding")
            st.session_state["intro_step"] = 0
            st.rerun()
    with col_w:
        if st.button("📖", key="nav_word", use_container_width=True, help="오늘의 금융 단어"):
            gs.go_to("word")
            st.rerun()
    with col_a:
        if st.button("💰", key="nav_allow", use_container_width=True, help="용돈 기입장"):
            gs.go_to("allowance")
            st.rerun()
    with col_s:
        if st.button("🐷", key="nav_save", use_container_width=True, help="저축 목표"):
            gs.go_to("savings")
            st.rerun()
    with col_p:
        if st.button("🏦", key="nav_prod", use_container_width=True, help="금융 상품 추천"):
            gs.go_to("products")
            st.rerun()
    with col_btn:
        if st.button("🎮 게임 시작", use_container_width=True, type="primary", key="nav_game"):
            if gs.world:
                gs.go_to("map")
            else:
                st.session_state["intro_step"] = 0
                gs.go_to("onboarding")
            st.rerun()
    st.divider()


# ── Intro step helpers ────────────────────────────────────────────────────────

def _step_back(target: int):
    st.markdown("<div style='margin-top:6px'></div>", unsafe_allow_html=True)
    c1, c2 = st.columns([1, 5])
    with c1:
        if st.button("← 이전", use_container_width=True):
            st.session_state["intro_step"] = target
            st.rerun()


def _intro_step0_name(gs: GameState):
    """Scene 0 – Shinhan splash + character selection."""
    st.markdown(
        """
        <div style="text-align:center;padding:44px 0 14px;animation:fadeUp .7s cubic-bezier(.34,1.56,.64,1);">
          <div style="display:inline-flex;align-items:center;gap:6px;
                      background:white;
                      border-radius:100px;
                      padding:7px 20px;font-size:.78rem;color:#003082;
                      letter-spacing:.8px;font-weight:900;margin-bottom:22px;
                      box-shadow:0 4px 16px rgba(0,0,0,.2);">
            <div style="width:18px;height:18px;background:linear-gradient(135deg,#0044CC,#0068FF);
                border-radius:50%;display:inline-flex;align-items:center;justify-content:center;
                font-size:9px;color:white;font-weight:900;">신</div>
            신한은행 금융교육 게임
          </div>
          <div style="font-size:5rem;animation:bounce 1.3s ease-out;display:block;margin-bottom:10px;
              filter:drop-shadow(0 0 20px rgba(255,214,10,.5));">🚀</div>
          <h1 style="font-size:3.4rem;font-weight:900;letter-spacing:-2px;margin:0 0 12px;
                     background:linear-gradient(135deg,#fff 30%,#FFD60A 70%,#FF6B6B 100%);
                     -webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;
                     line-height:1.1;">쏠어드벤쳐</h1>
          <p style="color:rgba(255,255,255,.8);font-size:1.1rem;margin:0;line-height:1.75;font-weight:700;">
            금융 지식으로 악당을 물리치는 어린이 모험! 🌟
          </p>
          <div style="display:flex;justify-content:center;gap:8px;margin-top:14px;flex-wrap:wrap;">
            <span style="background:rgba(255,107,107,.22);border:1.5px solid rgba(255,107,107,.5);
                border-radius:100px;padding:4px 14px;color:#FFB3B3;font-size:.78rem;font-weight:800;">🎮 퀴즈 배틀</span>
            <span style="background:rgba(255,214,10,.2);border:1.5px solid rgba(255,214,10,.4);
                border-radius:100px;padding:4px 14px;color:#FFE566;font-size:.78rem;font-weight:800;">🪙 코인 수집</span>
            <span style="background:rgba(6,214,160,.18);border:1.5px solid rgba(6,214,160,.4);
                border-radius:100px;padding:4px 14px;color:#A8F7E5;font-size:.78rem;font-weight:800;">📚 금융 지식</span>
          </div>
        </div>
        <div style="text-align:center;margin:24px 0 16px;">
          <span style="display:inline-flex;align-items:center;gap:6px;
                       background:linear-gradient(135deg,rgba(255,214,10,.25),rgba(255,107,107,.15));
                       border:2px solid rgba(255,214,10,.5);border-radius:100px;
                       padding:10px 24px;color:#FFE566;font-size:.95rem;font-weight:900;
                       box-shadow:0 4px 20px rgba(255,214,10,.25);">
            🌟 나의 캐릭터를 골라봐!
          </span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # 숨겨진 Streamlit 버튼 (DOM에는 있지만 height:0으로 보이지 않음)
    # components.html() 안의 JS가 window.parent.document로 찾아서 .click() 호출
    st.markdown(
        """
        <style>
        div:has(#char-btn-sentinel) + * { display: none !important; }
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.markdown('<div id="char-btn-sentinel"></div>', unsafe_allow_html=True)

    cols = st.columns(3)
    for i, ch in enumerate(CHARACTERS):
        with cols[i]:
            if st.button(ch["name"], key=f"char_{i}", use_container_width=True):
                gs.character_name = ch["name"]
                st.session_state["intro_step"] = 1
                st.rerun()

    # 실제로 보이는 카드 UI — iframe 안 JS가 부모 DOM 버튼을 클릭
    import streamlit.components.v1 as components

    cards_html = ""
    for ch in CHARACTERS:
        cards_html += (
            f'<div class="fq-card" onclick="selectChar(\'{ch["name"]}\')"'
            f' style="cursor:pointer;background:linear-gradient(160deg,rgba(255,255,255,.12),'
            f'rgba(255,255,255,.05));border:2px solid {ch["color"]}77;border-top:3px solid {ch["color"]}CC;'
            f'border-radius:28px;padding:30px 14px;text-align:center;flex:1;'
            f'transition:all .3s cubic-bezier(.34,1.56,.64,1);'
            f'box-shadow:0 6px 24px rgba(0,0,0,.18),inset 0 1px 0 rgba(255,255,255,.15);"'
            f' onmouseover="this.style.transform=\'translateY(-10px) scale(1.04)\';this.style.boxShadow=\'0 20px 52px rgba(0,0,0,.35),0 0 28px {ch["color"]}44\'"'
            f' onmouseout="this.style.transform=\'\';this.style.boxShadow=\'0 6px 24px rgba(0,0,0,.18)\'">'
            + _char_icon_html(ch)
            + f'<h3 style="color:{ch["color"]};margin:0 0 6px;font-size:1.12rem;font-weight:900;letter-spacing:-.2px;text-shadow:0 0 12px {ch["color"]}66;">{ch["name"]}</h3>'
            + f'<div style="width:36px;height:3px;background:linear-gradient(90deg,{ch["color"]},transparent);border-radius:100px;margin:0 auto 10px;"></div>'
            + f'<p style="color:rgba(255,255,255,.7);font-size:.82rem;margin:0;line-height:1.65;">{ch["desc"]}</p>'
            + '</div>'
        )

    components.html(
        f"""<!DOCTYPE html>
<html><head>
<style>
  body {{ margin:0; background:transparent; font-family:'Nunito','Segoe UI',sans-serif; }}
  .card-row {{ display:flex; gap:14px; padding:12px 4px 10px; }}
</style>
</head><body>
<div class="card-row">{cards_html}</div>
<script>
function selectChar(name) {{
  try {{
    var btns = Array.from(window.parent.document.querySelectorAll('button'));
    var btn = btns.find(function(b) {{ return b.textContent.trim() === name; }});
    if (btn) btn.click();
  }} catch(e) {{ console.error('selectChar:', e); }}
}}
</script>
</body></html>""",
        height=245,
    )

    # ── Quick feature menu ────────────────────────────────────────────
    st.markdown(
        """
        <div style="margin-top:32px;">
          <div style="text-align:center;margin-bottom:14px;">
            <span style="display:inline-block;background:rgba(255,255,255,.08);
                         border:1px solid rgba(255,255,255,.15);border-radius:100px;
                         padding:5px 16px;color:rgba(255,255,255,.55);font-size:.78rem;font-weight:700;">
              🛠️ 금융 도구
            </span>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    qc1, qc2, qc3, qc4, qc5 = st.columns(5)
    with qc1:
        if st.button("📖 금융\n단어", use_container_width=True, key="q_word"):
            gs.go_to("word")
            st.rerun()
    with qc2:
        if st.button("💰 용돈\n기입장", use_container_width=True, key="q_allow"):
            gs.go_to("allowance")
            st.rerun()
    with qc3:
        if st.button("🐷 저축\n목표", use_container_width=True, key="q_save"):
            gs.go_to("savings")
            st.rerun()
    with qc4:
        if st.button("🏦 금융\n상품", use_container_width=True, key="q_prod"):
            gs.go_to("products")
            st.rerun()
    with qc5:
        if st.button("📲 엄마\n조르기", use_container_width=True, key="q_joreogi"):
            gs.go_to("joreogi")
            st.rerun()


def _intro_step1_age(gs: GameState):
    """Scene 1 – first meeting + age selection."""
    name = gs.character_name
    char_emoji = next((c["emoji"] for c in CHARACTERS if c["name"] == name), "🌟")
    char_color = next((c["color"] for c in CHARACTERS if c["name"] == name), "#ffd700")
    st.markdown(
        f"""
        <div style="text-align:center;padding:32px 0 8px;animation:fadeUp .65s cubic-bezier(.34,1.56,.64,1);">
          <div style="font-size:3.8rem;animation:bounce 1.1s ease-out;display:block;">{char_emoji}</div>
          <h2 style="color:white;font-size:1.6rem;font-weight:900;margin:12px 0 4px;letter-spacing:-.5px;">
            {name}야, 만나서 반가워! 😊
          </h2>
        </div>
        <div class="fq-bubble" style="border-color:{char_color}44;background:linear-gradient(135deg,{char_color}0d,rgba(255,255,255,.05));">
          <div style="display:flex;align-items:center;gap:8px;margin-bottom:12px;">
            <div style="width:32px;height:32px;background:{char_color}33;border-radius:50%;
                        display:flex;align-items:center;justify-content:center;font-size:1.1rem;">💬</div>
            <span style="color:{char_color};font-size:.78rem;font-weight:800;letter-spacing:.5px;">쏠쏠이</span>
          </div>
          <p style="color:rgba(255,255,255,.85);font-size:1rem;line-height:1.95;margin:0;">
            나는 우주를 떠돌며 잃어버린 <b style="color:#ffd700;">쏠코인</b>을 모으는 <b style="color:#ffd700;">쏠쏠이</b>야! 🌟<br>
            모험 전에 <b style="color:white;">여행자 등록증</b>을 만들어야 딱 맞는 퀴즈를 골라줄 수 있어!
          </p>
        </div>
        <div style="text-align:center;margin:4px 0 18px;">
          <span style="display:inline-block;background:rgba(255,215,0,.15);border:1px solid rgba(255,215,0,.3);
                       border-radius:100px;padding:8px 20px;color:#ffd700;font-size:.92rem;font-weight:800;">
            🎒 몇 살 여행자야?
          </span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        """
        <style>
        div:has(#age-btn-sentinel) + * { display: none !important; }
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.markdown('<div id="age-btn-sentinel"></div>', unsafe_allow_html=True)

    cols = st.columns(3)
    for i, ag in enumerate(AGE_GROUPS):
        with cols[i]:
            if st.button(ag["label"], key=f"age_{i}", use_container_width=True):
                gs.age_group = ag["value"]
                st.session_state["intro_step"] = 2
                st.rerun()

    import streamlit.components.v1 as components

    # 캐릭터에 따라 나이 카드 아이콘을 사진으로 교체
    char_age_imgs = {
        "쏠쏠이": ("solsol1.png", "solsol2.png", "solsol3.png"),
        "몰리":   ("molly1.png",  "molly2.png",  "molly3.png"),
    }
    age_icons = []
    if gs.character_name in char_age_imgs:
        for fname in char_age_imgs[gs.character_name]:
            full = os.path.join(BASE, "assets", "characters", fname)
            if os.path.exists(full):
                with open(full, "rb") as f:
                    b64 = base64.b64encode(f.read()).decode()
                age_icons.append(
                    f'<img src="data:image/png;base64,{b64}"'
                    f' style="width:80px;height:80px;object-fit:contain;margin-bottom:10px;">'
                )
            else:
                age_icons.append(None)
    while len(age_icons) < 3:
        age_icons.append(None)

    age_cards_html = ""
    for i, ag in enumerate(AGE_GROUPS):
        icon = age_icons[i] or f'<div style="font-size:3.4rem;margin-bottom:10px;filter:drop-shadow(0 0 10px rgba(255,214,10,.5));">{ag["emoji"]}</div>'
        ai_badge = (
            '<div style="margin-top:11px;display:inline-flex;align-items:center;gap:5px;'
            'background:linear-gradient(135deg,rgba(99,102,241,.35),rgba(168,85,247,.25));'
            'border:1.5px solid rgba(168,85,247,.6);border-radius:100px;'
            'padding:5px 11px;font-size:.7rem;font-weight:900;color:#c4b5fd;'
            'letter-spacing:.03em;animation:pulse 2s ease-in-out infinite;">'
            '🤖 AI 퀴즈 생성!</div>'
        ) if i == 2 else ""
        age_cards_html += (
            f'<div class="fq-card" onclick="selectAge(\'{ag["label"]}\')"'
            f' style="cursor:pointer;background:linear-gradient(160deg,rgba(255,255,255,.12),'
            f'rgba(255,255,255,.05));border:2px solid rgba(255,214,10,.45);border-top:3px solid rgba(255,214,10,.8);'
            f'border-radius:28px;padding:30px 14px;text-align:center;flex:1;'
            f'transition:all .3s cubic-bezier(.34,1.56,.64,1);'
            f'box-shadow:0 6px 24px rgba(0,0,0,.18),inset 0 1px 0 rgba(255,255,255,.15);"'
            f' onmouseover="this.style.transform=\'translateY(-10px) scale(1.04)\';this.style.boxShadow=\'0 20px 52px rgba(0,0,0,.35),0 0 28px rgba(255,214,10,.3)\'"'
            f' onmouseout="this.style.transform=\'\';this.style.boxShadow=\'0 6px 24px rgba(0,0,0,.18)\'">'
            + icon
            + f'<h3 style="color:#FFE566;margin:0 0 6px;font-size:1.12rem;font-weight:900;letter-spacing:-.2px;text-shadow:0 0 12px rgba(255,214,10,.5);">{ag["label"]}</h3>'
            + f'<div style="width:36px;height:3px;background:linear-gradient(90deg,#FFD60A,transparent);border-radius:100px;margin:0 auto 10px;"></div>'
            + f'<p style="color:rgba(255,255,255,.7);font-size:.82rem;margin:0;line-height:1.65;">{ag["desc"]}</p>'
            + ai_badge
            + '</div>'
        )

    components.html(
        f"""<!DOCTYPE html>
<html><head>
<style>
  body {{ margin:0; background:transparent; font-family:'Nunito','Segoe UI',sans-serif; }}
  .card-row {{ display:flex; gap:14px; padding:12px 4px 10px; }}
</style>
</head><body>
<div class="card-row">{age_cards_html}</div>
<script>
function selectAge(label) {{
  try {{
    var btns = Array.from(window.parent.document.querySelectorAll('button'));
    var btn = btns.find(function(b) {{ return b.textContent.trim() === label; }});
    if (btn) btn.click();
  }} catch(e) {{ console.error('selectAge:', e); }}
}}
</script>
</body></html>""",
        height=245,
    )

    _step_back(0)


def _intro_step2_world(gs: GameState):
    """Scene 2 – world / theme selection."""
    name = gs.character_name
    st.markdown(
        f"""
        <div style="text-align:center;padding:30px 0 10px;animation:fadeUp .65s cubic-bezier(.34,1.56,.64,1);">
          <div style="font-size:3rem;animation:floatY 2.4s ease-in-out infinite;display:block;">🗺️</div>
          <h2 style="color:white;font-size:1.55rem;font-weight:900;margin:12px 0 4px;letter-spacing:-.5px;">
            어떤 세계로 모험할까? ✨
          </h2>
        </div>
        <div class="fq-bubble">
          <div style="display:flex;align-items:center;gap:8px;margin-bottom:12px;">
            <div style="width:32px;height:32px;background:rgba(255,215,0,.2);border-radius:50%;
                        display:flex;align-items:center;justify-content:center;font-size:1.1rem;">💬</div>
            <span style="color:#ffd700;font-size:.78rem;font-weight:800;letter-spacing:.5px;">쏠쏠이</span>
          </div>
          <p style="color:rgba(255,255,255,.85);font-size:1rem;line-height:1.9;margin:0;">
            좋아! <b style="color:#ffd700;">{name}</b>의 마음이 끌리는 <b style="color:white;">모험 세계</b>를 골라줘. 🌈<br>
            세계마다 다른 악당과 쏠코인이 기다리고 있어!
          </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    import streamlit.components.v1 as components

    st.markdown(
        """
        <style>
        div:has(#world-btn-sentinel) + * { display: none !important; }
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.markdown('<div id="world-btn-sentinel"></div>', unsafe_allow_html=True)

    cols = st.columns(3)
    for i, w in enumerate(INTRO_WORLDS):
        with cols[i]:
            if st.button(f"{w['emoji']} {w['name']}", key=f"world_{i}", use_container_width=True):
                gs.world = w["id"]
                st.session_state["intro_step"] = 3
                st.rerun()

    world_cards_html = ""
    for w in INTRO_WORLDS:
        c = w["color"]
        badge = (
            f'<div style="margin:8px 0 4px"><span style="background:{c}33;color:{c};'
            f'font-size:.7rem;padding:4px 12px;border-radius:100px;font-weight:900;'
            f'letter-spacing:.3px;border:1.5px solid {c}55;">📈 주식·투자</span></div>'
            if w["id"] == "space"
            else '<div style="height:8px"></div>'
        )
        label = f'{w["emoji"]} {w["name"]}'
        world_cards_html += (
            f'<div class="fq-card" onclick="selectWorld(\'{label}\')"'
            f' style="cursor:pointer;background:linear-gradient(160deg,rgba(255,255,255,.12),'
            f'rgba(255,255,255,.05));border:2px solid {c}66;border-top:3px solid {c}CC;'
            f'border-radius:28px;padding:24px 14px;text-align:center;display:flex;flex-direction:column;'
            f'align-items:center;transition:all .3s cubic-bezier(.34,1.56,.64,1);'
            f'box-shadow:0 6px 24px rgba(0,0,0,.18),inset 0 1px 0 rgba(255,255,255,.15);"'
            f' onmouseover="this.style.transform=\'translateY(-10px) scale(1.04)\';this.style.boxShadow=\'0 20px 52px rgba(0,0,0,.35),0 0 28px {c}44\'"'
            f' onmouseout="this.style.transform=\'\';this.style.boxShadow=\'0 6px 24px rgba(0,0,0,.18)\'">'
            + f'<div style="font-size:3.4rem;margin-bottom:4px;filter:drop-shadow(0 0 12px {c}55);">{w["emoji"]}</div>'
            + badge
            + f'<h3 style="color:{c};margin:0 0 8px;font-size:1.08rem;font-weight:900;letter-spacing:-.2px;text-shadow:0 0 12px {c}44;">{w["name"]}</h3>'
            + f'<div style="background:rgba(255,107,107,.18);border:1.5px solid rgba(255,107,107,.4);'
            f'border-radius:100px;padding:4px 12px;font-size:.74rem;color:#FFB3B3;font-weight:800;margin-bottom:10px;">'
            f'👿 {w["villain"]}</div>'
            + f'<p style="color:rgba(255,255,255,.7);font-size:.81rem;margin:0;line-height:1.7;flex:1;">{w["desc"]}</p>'
            + '</div>'
        )

    components.html(
        f"""<!DOCTYPE html>
<html><head>
<style>
  body {{ margin:0; background:transparent; font-family:'Nunito','Segoe UI',sans-serif; }}
  .card-row {{
    display:flex; gap:14px; padding:12px 4px 10px;
    align-items:stretch;
  }}
  .fq-card {{ flex:1; box-sizing:border-box; }}
</style>
</head><body>
<div class="card-row">{world_cards_html}</div>
<script>
function selectWorld(label) {{
  try {{
    var btns = Array.from(window.parent.document.querySelectorAll('button'));
    var btn = btns.find(function(b) {{ return b.textContent.trim() === label; }});
    if (btn) btn.click();
  }} catch(e) {{ console.error('selectWorld:', e); }}
}}
</script>
</body></html>""",
        height=320,
    )

    _step_back(1)


def _intro_step3_finale(gs: GameState):
    """Scene 3 – final narrative + start."""
    name = gs.character_name
    world_info = next((w for w in INTRO_WORLDS if w["id"] == gs.world), INTRO_WORLDS[0])
    c = world_info["color"]
    extra_line = (
        '<br>주식·투자 퀴즈를 풀고 최신 주식 뉴스도 확인해봐! 📈'
        if world_info["id"] == "space" else ""
    )

    st.markdown(
        f"""
        <div style="text-align:center;padding:36px 0 10px;animation:fadeUp .7s cubic-bezier(.34,1.56,.64,1);">
          <div style="font-size:4rem;animation:bounce 1.1s ease-out;display:block;margin-bottom:10px;">{world_info['emoji']}</div>
          <div style="display:inline-block;background:{c}22;border:1px solid {c}55;border-radius:100px;
                      padding:6px 20px;color:{c};font-size:.85rem;font-weight:800;margin-bottom:14px;">
            준비 완료! 🎉
          </div>
          <h2 style="color:white;font-weight:900;font-size:1.7rem;margin:0;letter-spacing:-.6px;">
            모험을 시작하자!
          </h2>
        </div>
        <div class="fq-bubble" style="border-color:{c}44;background:linear-gradient(135deg,{c}12,rgba(255,255,255,.05));">
          <div style="display:flex;align-items:center;gap:8px;margin-bottom:14px;">
            <div style="width:32px;height:32px;background:{c}33;border-radius:50%;
                        display:flex;align-items:center;justify-content:center;font-size:1.1rem;">💬</div>
            <span style="color:{c};font-size:.78rem;font-weight:800;letter-spacing:.5px;">쏠쏠이</span>
          </div>
          <p style="color:rgba(255,255,255,.88);font-size:1rem;line-height:2;margin:0;">
            좋아, <b style="color:{c};">{name}</b>아! 드디어 모험이 시작돼! 🎉<br>
            목적지는 <b style="color:{c};font-size:1.06rem;">「{world_info['name']}」</b>!<br>
            <span style="display:inline-block;background:rgba(239,68,68,.12);border:1px solid rgba(239,68,68,.28);
                         border-radius:10px;padding:6px 12px;margin-top:6px;color:#fca5a5;font-size:.9rem;">
              ⚠️ <b style="color:#ef4444;">{world_info['villain']}</b>이(가) 쏠코인을 훔쳐갔어! 금융 퀴즈로 되찾자! 💪
            </span>
            {f'<br><span style="color:rgba(255,255,255,.65);font-size:.88rem;">{extra_line.strip("<br>")}</span>' if extra_line else ""}
          </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    _, mid, _ = st.columns([1, 2, 1])
    with mid:
        if st.button("⚔️ 모험 시작하기!", use_container_width=True, type="primary"):
            saved_name  = gs.character_name
            saved_age   = gs.age_group
            saved_world = gs.world
            st.session_state["intro_step"] = 0
            # 이전 저장 파일 삭제 후 초기화 (새 게임 시작)
            try:
                from game.persistence import delete_save
                delete_save()
            except Exception:
                pass
            gs.reset()
            gs.character_name = saved_name
            gs.age_group      = saved_age
            gs.world          = saved_world
            gs.go_to("map")
            st.rerun()

    _step_back(2)


# ── Page: Onboarding ──────────────────────────────────────────────────────────

def page_onboarding(gs: GameState, worlds: list):
    _inject_intro_css()

    step = st.session_state.get("intro_step", 0)
    _render_shinhan_logo_bar(step)

    if step == 0:
        _intro_step0_name(gs)
    elif step == 1:
        _intro_step1_age(gs)
    elif step == 2:
        _intro_step2_world(gs)
    else:
        _intro_step3_finale(gs)


# ── Game event handler ────────────────────────────────────────────────────────

def _handle_game_event(event: dict, gs: GameState, badge_engine: BadgeEngine):
    etype = event.get("type")

    if etype == "QUIZ_RESULT":
        total = event.get("total_coins", gs.coins)
        gs.coins = max(gs.coins, total)                     # sync (game is source of truth)
        if event.get("correct") and event.get("mission_id"):
            gs.complete_mission(event["mission_id"])
        if event.get("concept"):
            history = st.session_state.setdefault("_answer_history", [])
            history.append({"concept": event["concept"], "correct": bool(event.get("correct"))})
        _post_mission_checks(gs, badge_engine)
        if event.get("correct"):
            st.toast(f"🎉 정답! +{event.get('coins_earned',0)} 코인")
        else:
            st.toast("😅 틀렸어요. 다시 도전해봐요!")
        # st.rerun() 호출을 의도적으로 생략 — 즉시 rerun하면 배지 알림이 사라짐

    elif etype == "STAGE2_WIN":
        gs.coins = max(gs.coins, event.get("total_coins", gs.coins))
        if "stage2_clear" not in gs.completed_missions:
            gs.complete_mission("stage2_clear")
        _post_mission_checks(gs, badge_engine)
        _save_progress(gs)

    elif etype == "COIN_COLLECTED":
        gs.coins = max(gs.coins, event.get("total_coins", gs.coins))

    elif etype == "WORLD_CLEAR":
        world_ko = {
            "dinosaur": "공룡 정글", "space": "우주 정거장",
            "magic": "마법 왕국",   "ocean": "심해 왕국",
        }.get(event.get("world", ""), "세계")
        gs.coins = max(gs.coins, event.get("final_coins", gs.coins))
        milestone = f"world_clear_{event.get('world', '')}"
        if milestone not in gs.completed_missions:
            gs.complete_mission(milestone)
        _post_mission_checks(gs, badge_engine)
        _save_progress(gs)
        st.balloons()
        st.success(f"🏆 {world_ko} 클리어! 보스를 물리쳤어요!")
        # st.rerun() 제거 — 게임 도중 setVal이 오면 rerun이 게임을 리셋시킴

    elif etype == "GAME_OVER":
        gs.coins = event.get("final_coins", gs.coins)
        for mid in event.get("missions_completed", []):
            if mid not in gs.completed_missions:
                gs.complete_mission(mid)
        _post_mission_checks(gs, badge_engine)
        gs.go_to("report")
        st.rerun()

    elif etype == "NEWS_REQUEST":
        gs.coins = max(gs.coins, event.get("final_coins", gs.coins))
        world = event.get("world", gs.world or "space")
        milestone = f"world_clear_{world}"
        if milestone not in gs.completed_missions:
            gs.complete_mission(milestone)
        _post_mission_checks(gs, badge_engine)
        _save_progress(gs)
        gs.go_to("news")
        st.rerun()


# ── Page: Map ─────────────────────────────────────────────────────────────────

def page_map(
    gs: GameState, worlds: list, missions: list, badge_engine: BadgeEngine
):
    world = get_world(worlds, gs.world)
    if not world:
        gs.go_to("onboarding")
        st.rerun()
        return

    inject_css(gs.world)
    _render_top_nav(gs)

    # Missions for this world (age-group filtered)
    world_missions = get_world_missions(missions, world["zones"], gs.age_group)

    # ── Preload AI quizzes once per world (백그라운드 캐시 우선 확인) ──
    quiz_cache_key = f"_quizzes_{gs.world}"
    if not st.session_state.get(quiz_cache_key):
        with _BG_LOCK:
            bg_result = _BG_CACHE.get(quiz_cache_key)
        if bg_result is not None:
            st.session_state[quiz_cache_key] = bg_result
        else:
            with st.spinner("🤖 AI 퀴즈 생성 중... (처음 한 번만)"):
                try:
                    st.session_state[quiz_cache_key] = preload_quizzes(
                        gs.world, gs.age_group, gs.character_name
                    )
                except Exception:
                    st.session_state[quiz_cache_key] = []
    world_quizzes = st.session_state.get(quiz_cache_key, [])

    # ── Widen container for 800 px canvas ──────
    st.markdown(
        """
        <style>
        .block-container {
            max-width: 900px !important;
            padding-left: 1.5rem !important;
            padding-right: 1.5rem !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    # ── Render Phaser game ──────────────────────
    battle_test = st.session_state.pop("battle_test_mode", False)
    result = render_phaser_game(
        world=gs.world,
        character_name=gs.character_name,
        age_group=gs.age_group,
        coins=gs.coins,
        level=gs.level,
        completed_missions=list(gs.completed_missions),
        missions=world_missions,
        quizzes=world_quizzes,
        key=f"phaser_{gs.world}",
        battle_test=battle_test,
    )

    # ── Event deduplication ───────────────────────────────────────────────────
    # Phaser component re-emits the last value on every st.rerun().
    # Guard with a compound key (ts + type + mission_id) stored as a bounded
    # list so two rapid-fire events with the same ts are still distinguished.
    if result:
        ev_key = "{}|{}|{}".format(
            result.get("ts", 0),
            result.get("type", ""),
            result.get("mission_id", ""),
        )
        _done = st.session_state.get("_processed_ev", [])
        if ev_key in _done:
            result = None  # already handled on a previous run
        else:
            # Keep list bounded to last 40 events
            st.session_state["_processed_ev"] = (_done + [ev_key])[-40:]

    if result:
        _handle_game_event(result, gs, badge_engine)

    # ── Bottom navigation ────────────────────────
    st.markdown("<div style='margin-top:8px'></div>", unsafe_allow_html=True)
    b_col1, b_col2 = st.columns(2)
    with b_col1:
        if st.button("🔙 세계 다시 선택", use_container_width=True):
            st.session_state["intro_step"] = 2
            gs.go_to("onboarding")
            st.rerun()
    with b_col2:
        if _total_completed() > 0:
            if st.button("📊 결과 리포트", use_container_width=True, type="secondary"):
                gs.go_to("report")
                st.rerun()


# ── Page: Mission ─────────────────────────────────────────────────────────────

def page_mission(
    gs: GameState, worlds: list, missions: list, badge_engine: BadgeEngine
):
    world = get_world(worlds, gs.world)
    if not world or not gs.current_zone:
        gs.go_to("map")
        st.rerun()
        return

    zone = next((z for z in world["zones"] if z["id"] == gs.current_zone), None)
    if not zone:
        gs.go_to("map")
        st.rerun()
        return

    inject_css(gs.world)
    render_header(gs.character_name, gs.coins, gs.level, world["emoji"], gs.world)

    recommender = get_recommender()
    difficulty = recommender.recommend_difficulty(gs)
    diff_label = {"easy": "⭐ 쉬움", "medium": "⭐⭐ 보통", "hard": "⭐⭐⭐ 어려움"}.get(difficulty, "⭐⭐")

    st.markdown(f"### {zone['emoji']} {zone['name']}")
    st.caption(f"난이도: {diff_label}")
    render_concept_card(zone["concept"], zone["concept_desc"], zone["emoji"])
    st.divider()

    # ── Load mission ──────────────────────────────────────────────────────────
    mission = None
    is_dynamic = False

    if has_api_key():
        cached = st.session_state.get("dynamic_mission")
        cached_zone = st.session_state.get("_last_zone_for_dynamic")
        if cached and cached_zone == gs.current_zone:
            mission = cached
            is_dynamic = True
        else:
            generator = get_generator()
            with st.spinner("🤖 AI가 맞춤 미션을 만들고 있어요..."):
                mission = generator.generate_mission(
                    gs.world, gs.current_zone, gs.age_group,
                    _total_completed(), gs.character_name or "탐험가",
                )
            if mission:
                st.session_state["dynamic_mission"] = mission
                st.session_state["_last_zone_for_dynamic"] = gs.current_zone
                is_dynamic = True
            else:
                st.warning("AI 미션 생성에 실패했어요. 기본 미션으로 진행해요.")

    if not mission:
        zone_missions = get_zone_missions(missions, gs.current_zone, gs.age_group)
        if not zone_missions:
            st.warning("이 구역에 미션이 없어요.")
            if st.button("← 맵으로 돌아가기"):
                gs.go_to("map")
                st.rerun()
            return
        undone = [m for m in zone_missions if m["id"] not in gs.completed_missions]
        pool = undone if undone else zone_missions
        idx = gs.current_mission_idx if gs.current_mission_idx < len(pool) else 0
        mission = pool[idx]

    # ── Concept card ──────────────────────────────────────────────────────────
    card = mission.get("concept_card", {})
    if card:
        st.markdown(
            f"""
            <div style="background:#f0fdf4; border-left:4px solid #22c55e;
                        border-radius:10px; padding:12px 16px; margin-bottom:14px;">
                <b>{card.get('emoji','')} {card.get('title','')}</b><br>
                <span style="color:#166534; font-size:0.95rem;">{card.get('body','')}</span>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # ── Question ──────────────────────────────────────────────────────────────
    st.markdown(
        f"""
        <div style="font-size:1.25rem; font-weight:600; line-height:1.6;
                    background:#fffbeb; border-radius:12px;
                    padding:16px 20px; margin:10px 0;">
            ❓ {mission['question']}
        </div>
        """,
        unsafe_allow_html=True,
    )

    already_done = (
        st.session_state.get(f"dynamic_done_{gs.current_zone}")
        if is_dynamic
        else mission.get("id", "") in gs.completed_missions
    )

    # ── Result state ──────────────────────────────────────────────────────────
    if gs.mission_answered or already_done:
        last = gs.last_answer
        if last:
            chosen = next((c for c in mission["choices"] if c["id"] == last), None)
            if chosen:
                render_mission_result(chosen["correct"], chosen["feedback"], chosen["coins"])

        st.divider()
        col1, col2 = st.columns(2)
        with col1:
            if st.button("🗺️ 맵으로 돌아가기", use_container_width=True, type="primary"):
                gs.mission_answered = False
                gs.last_answer = None
                st.session_state.pop("dynamic_mission", None)
                gs.go_to("map")
                st.rerun()
        with col2:
            if is_dynamic and not already_done:
                if st.button("🔄 다른 AI 미션 도전!", use_container_width=True):
                    gs.mission_answered = False
                    gs.last_answer = None
                    st.session_state.pop("dynamic_mission", None)
                    st.rerun()
            elif not is_dynamic:
                zone_all = get_zone_missions(missions, gs.current_zone, gs.age_group)
                next_m = next(
                    (m for m in zone_all if m["id"] not in gs.completed_missions), None
                )
                if next_m and (not already_done or next_m.get("id") != mission.get("id")):
                    if st.button("➡️ 다음 미션", use_container_width=True):
                        gs.current_mission_idx = zone_all.index(next_m)
                        gs.mission_answered = False
                        gs.last_answer = None
                        st.rerun()
        return

    # ── Choices ───────────────────────────────────────────────────────────────
    st.markdown("#### 선택하세요")
    for choice in mission["choices"]:
        label = f"{choice['id'].upper()}. {choice['text']}"
        if st.button(label, key=f"choice_{choice['id']}", use_container_width=True):
            gs.last_answer = choice["id"]
            gs.mission_answered = True

            gs.add_coins(choice["coins"], label=zone["name"])
            show_coin_earned(choice["coins"])

            recommender.log_answer(
                gs.current_zone, zone["concept"], choice.get("correct", False)
            )

            if choice.get("correct"):
                if is_dynamic:
                    st.session_state[f"dynamic_done_{gs.current_zone}"] = True
                    gs.complete_mission(f"dynamic_{gs.current_zone}")
                else:
                    gs.complete_mission(mission.get("id", f"static_{gs.current_zone}"))

                if choice["coins"] > 0:
                    render_coin_animation(choice["coins"])

                _post_mission_checks(gs, badge_engine)

            st.rerun()

    st.divider()
    if st.button("← 맵으로 돌아가기"):
        gs.mission_answered = False
        gs.last_answer = None
        st.session_state.pop("dynamic_mission", None)
        gs.go_to("map")
        st.rerun()


# ── Page: Report (Parent Report) ──────────────────────────────────────────────

def page_report(gs: GameState, worlds: list, missions: list, badge_engine: BadgeEngine):
    inject_css(gs.world or "ocean")
    _render_top_nav(gs)

    world = get_world(worlds, gs.world)
    world_emoji = world["emoji"] if world else "🗺️"
    render_header(gs.character_name, gs.coins, gs.level, world_emoji, gs.world or "ocean")

    import importlib
    import pages.parent_report as _pr
    importlib.reload(_pr)
    _pr.render_parent_report(
        gs,
        get_generator(),
        badge_engine,
        get_recommender(),
    )

    st.divider()
    if st.button("🗺️ 계속 탐험하기", use_container_width=True, type="secondary"):
        gs.go_to("map")
        st.rerun()


# ── Page: Stock News ─────────────────────────────────────────────────────────

def page_news(gs: GameState):
    inject_css(gs.world or "space")
    _render_top_nav(gs)

    # ── 동요 배우기 mode ──────────────────────────────────────────────────────
    if st.session_state.get("show_donyo"):
        st.markdown("## 🎵 동요 배우기")
        st.markdown("신한 쏠어드벤쳐 테마송을 즐겨봐요! 🌟")
        music_path = os.path.join(BASE, "components", "phaser_game", "frontend", "music", "shinhan.mp4")
        if os.path.exists(music_path):
            import base64
            with open(music_path, "rb") as _f:
                video_b64 = base64.b64encode(_f.read()).decode()
            st.markdown(
                f'<video autoplay controls style="width:100%;border-radius:16px;max-height:480px;background:#000;">'
                f'<source src="data:video/mp4;base64,{video_b64}" type="video/mp4">'
                f'</video>',
                unsafe_allow_html=True,
            )
        else:
            st.warning("음악 파일을 찾을 수 없어요.")
        st.divider()
        col1, col2, col3 = st.columns(3)
        with col1:
            if st.button("📰 뉴스 보기", use_container_width=True):
                st.session_state.pop("show_donyo", None)
                st.rerun()
        with col2:
            if st.button("🏆 결과 보기", use_container_width=True, type="primary"):
                st.session_state.pop("show_donyo", None)
                gs.go_to("result")
                st.rerun()
        with col3:
            if st.button("🗺️ 계속 탐험하기", use_container_width=True):
                st.session_state.pop("show_donyo", None)
                gs.go_to("map")
                st.rerun()
        return

    # ── Normal news view ──────────────────────────────────────────────────────
    st.markdown(
        """
        <style>
        .block-container { max-width: 780px !important; }
        .news-card {
            background: rgba(255,255,255,.1);
            backdrop-filter: blur(28px);
            -webkit-backdrop-filter: blur(28px);
            border: 2px solid rgba(255,255,255,.2);
            border-top: 3px solid rgba(255,255,255,.45);
            border-radius: 28px;
            padding: 24px 26px;
            margin-bottom: 18px;
            box-shadow: 0 12px 40px rgba(0,0,0,.18), inset 0 1px 0 rgba(255,255,255,.15);
            transition: all .28s cubic-bezier(.34,1.56,.64,1);
            position: relative; overflow: hidden;
        }
        .news-card:hover { transform: translateY(-4px) scale(1.01); box-shadow: 0 20px 56px rgba(0,0,0,.25); }
        .news-header { display: flex; align-items: flex-start; gap: 16px; margin-bottom: 14px; }
        .news-emoji-box {
            width: 56px; height: 56px; min-width: 56px; border-radius: 18px;
            background: linear-gradient(135deg, rgba(255,107,107,.25), rgba(255,142,83,.2));
            border: 1.5px solid rgba(255,255,255,.25);
            display: flex; align-items: center; justify-content: center; font-size: 2rem;
        }
        .news-title { font-size: 1.08rem; font-weight: 900; color: white; line-height: 1.4; margin: 0; }
        .news-summary { font-size: .94rem; color: rgba(255,255,255,.78); line-height: 1.9; margin-bottom: 14px; }
        .news-lesson {
            display: inline-flex; align-items: center; gap: 8px;
            background: linear-gradient(135deg, rgba(255,214,10,.2), rgba(255,163,26,.15));
            border: 1.5px solid rgba(255,214,10,.4);
            border-radius: 14px; padding: 9px 16px; margin-bottom: 12px;
            font-size: .88rem; color: #FFE566; font-weight: 800; line-height: 1.5;
        }
        .news-link a {
            font-size: .83rem; color: rgba(160,210,255,.85); text-decoration: none;
            font-weight: 700; display: inline-flex; align-items: center; gap: 5px;
        }
        .news-link a:hover { color: white; }
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        '<div style="padding:12px 0 8px;text-align:center;">'
        '<h2 style="color:white;font-size:2rem;font-weight:900;letter-spacing:-.6px;margin:0 0 8px;">📰 오늘의 주식 뉴스</h2>'
        '<p style="color:rgba(255,255,255,.65);font-size:.96rem;margin:0;">쏠쏠이가 어린이도 이해하기 쉽게 설명해줄게요! 🌟</p>'
        '</div>',
        unsafe_allow_html=True,
    )
    st.divider()

    cache_key = "_kids_news_cache"
    news_items = st.session_state.get(cache_key)

    if not news_items:
        with _BG_LOCK:
            bg_news = _BG_CACHE.get(cache_key)
        if bg_news:
            news_items = bg_news
            st.session_state[cache_key] = bg_news
        else:
            with st.spinner("📡 최신 뉴스를 가져오는 중... (잠깐만 기다려줘!)"):
                try:
                    from ai.news_crawler import get_kids_news
                    news_items = get_kids_news(
                        n=5,
                        age_group=gs.age_group,
                        character_name="쏠쏠이",
                    )
                    st.session_state[cache_key] = news_items
                except Exception as e:
                    st.error(f"뉴스를 불러오지 못했어요. 잠시 후 다시 시도해줘요! ({e})")
                    news_items = []

    is_senior = (gs.age_group == "senior")

    if news_items:
        for i, item in enumerate(news_items):
            link_html = (
                f'<div class="news-link"><a href="{item["link"]}" target="_blank" rel="noopener">🔗 원문 기사 보기</a></div>'
                if item.get("link") else ""
            )
            st.markdown(
                '<div class="news-card">'
                '<div class="news-header">'
                f'<div class="news-emoji-box">{item.get("emoji", "📰")}</div>'
                f'<div class="news-title">{item.get("title", "")}</div>'
                '</div>'
                f'<div class="news-summary">{item.get("summary", "")}</div>'
                f'<div class="news-lesson">💡 {item.get("lesson", "")}</div>'
                f'{link_html}'
                '</div>',
                unsafe_allow_html=True,
            )

            # ── Step 3: 뉴스 기반 퀴즈 (13세 이상 전용) ──────────────────────
            if is_senior:
                _quiz_open    = st.session_state.get("_news_quiz_open")
                _ans_key      = f"_news_quiz_ans_{i}"
                _data_key     = f"_news_quiz_data_{i}"

                if _quiz_open == i:
                    quiz = st.session_state.get(_data_key)
                    if quiz is None:
                        with st.spinner("🤖 AI가 퀴즈를 만들고 있어요..."):
                            _api_key = (
                                st.session_state.get("openai_api_key")
                                or os.environ.get("OPENAI_API_KEY")
                            )
                            from ai.news_crawler import generate_news_quiz
                            quiz = generate_news_quiz(item, gs.age_group, api_key=_api_key)
                            if quiz:
                                st.session_state[_data_key] = quiz

                    if quiz:
                        st.markdown(
                            '<div style="background:rgba(99,102,241,.12);border:1.5px solid rgba(168,85,247,.45);'
                            'border-radius:16px;padding:16px 20px;margin-bottom:8px;">'
                            f'<div style="font-size:.82rem;font-weight:900;color:#c4b5fd;margin-bottom:8px;">🤖 AI 퀴즈</div>'
                            f'<div style="font-size:.97rem;font-weight:800;color:white;line-height:1.6;">'
                            f'{quiz["question"]}</div>'
                            '</div>',
                            unsafe_allow_html=True,
                        )
                        answered = st.session_state.get(_ans_key)
                        if not answered:
                            q_cols = st.columns(len(quiz["choices"]))
                            for j, choice in enumerate(quiz["choices"]):
                                with q_cols[j]:
                                    _markers = ['①','②','③','④']
                                    btn_label = f"{_markers[j] if j < len(_markers) else str(j+1)} {choice['text']}"
                                    if st.button(btn_label, key=f"_nq_{i}_{j}", use_container_width=True):
                                        st.session_state[_ans_key] = choice
                                        gs.add_coins(
                                            choice.get("coins", -5),
                                            f"뉴스퀴즈 {'정답' if choice.get('correct') else '오답'}",
                                        )
                                        st.rerun()
                        else:
                            is_correct = answered.get("correct", False)
                            coins      = answered.get("coins", -5)
                            bg_rgb     = "6,214,160" if is_correct else "239,71,111"
                            icon_      = "🎉" if is_correct else "😢"
                            label_     = "정답!" if is_correct else "오답!"
                            st.markdown(
                                f'<div style="background:rgba({bg_rgb},.15);border:1.5px solid rgba({bg_rgb},.45);'
                                f'border-radius:12px;padding:14px 18px;margin-bottom:8px;">'
                                f'<span style="color:{"#06D6A0" if is_correct else "#EF476F"};font-weight:900;">'
                                f'{icon_} {label_}</span> '
                                f'<span style="color:white;">{"+" if coins > 0 else ""}{coins}코인</span><br>'
                                f'<span style="color:rgba(255,255,255,.8);font-size:.88rem;">'
                                f'{answered.get("feedback","")}</span></div>',
                                unsafe_allow_html=True,
                            )
                            cc = quiz.get("concept_card", {})
                            if cc:
                                st.markdown(
                                    f'<div style="background:rgba(255,209,102,.1);border:1.5px solid rgba(255,209,102,.35);'
                                    f'border-radius:12px;padding:12px 18px;margin-bottom:10px;">'
                                    f'{cc.get("emoji","💡")} '
                                    f'<strong style="color:#FFD166;">{cc.get("title","")}</strong>'
                                    f' — <span style="color:rgba(255,255,255,.8);font-size:.88rem;">'
                                    f'{cc.get("body","")}</span></div>',
                                    unsafe_allow_html=True,
                                )
                            if st.button("✅ 퀴즈 닫기", key=f"_nq_close_{i}"):
                                st.session_state.pop("_news_quiz_open", None)
                                st.rerun()
                    else:
                        st.warning("API 키가 없거나 퀴즈를 생성하지 못했어요.")
                        if st.button("닫기", key=f"_nq_err_{i}"):
                            st.session_state.pop("_news_quiz_open", None)
                            st.rerun()
                else:
                    if st.button("🤖 AI 퀴즈 풀기", key=f"_nq_open_{i}"):
                        st.session_state["_news_quiz_open"] = i
                        st.session_state.pop(_ans_key, None)
                        st.rerun()
    else:
        st.info("현재 뉴스를 불러올 수 없어요. 잠시 후 다시 시도해주세요!")

    st.divider()
    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("🎵 동요 배우기", use_container_width=True):
            st.session_state["show_donyo"] = True
            st.rerun()
    with col2:
        if st.button("🔄 뉴스 새로고침", use_container_width=True):
            st.session_state.pop("_kids_news_cache", None)
            st.rerun()
    with col3:
        if st.button("🗺️ 계속 탐험하기", use_container_width=True):
            gs.go_to("map")
            st.rerun()

    if st.button("📊 결과 리포트 보기", use_container_width=True, type="primary"):
        gs.go_to("report")
        st.rerun()


# ── Page: Game Result ────────────────────────────────────────────────────────

def page_result(gs: GameState):
    inject_css(gs.world or "space")
    _render_top_nav(gs)

    name   = gs.character_name or "쏠쏠이"
    coins  = gs.coins
    done   = len(gs.completed_missions)

    evolutions = CHAR_EVOLUTION.get(name, CHAR_EVOLUTION["쏠쏠이"])
    tier = 2 if coins >= 100 else (1 if coins >= 50 else 0)
    evo  = evolutions[tier]

    tc  = ["#fbbf24", "#f59e0b", "#818cf8"][tier]
    tbg = ["rgba(251,191,36,.09)", "rgba(245,158,11,.11)", "rgba(129,140,248,.13)"][tier]

    stars = "⭐" * (tier + 1) + "✩" * (2 - tier)
    congrats = [
        f"코인 {coins}개! 다음엔 더 많이 모아봐요 🌱",
        f"코인 {coins}개! 금융 실력이 쑥쑥! 🚀",
        f"코인 {coins}개! 진정한 마스터! 🏆",
    ][tier]
    medal  = ["🥉", "🥈", "🥇"][tier]
    wko    = {"space": "별빛 금융 은하", "dinosaur": "공룡 정글",
              "magic": "마법왕국", "ocean": "파도 저금섬"}.get(gs.world or "space", "핀퀘스트")
    tips   = WORLD_FINANCIAL_TIPS.get(gs.world or "space", WORLD_FINANCIAL_TIPS["space"])

    tier_colors  = ["#fbbf24", "#a78bfa", "#818cf8"]
    tier_glow    = ["rgba(251,191,36,.6)", "rgba(167,139,250,.6)", "rgba(129,140,248,.7)"]
    tier_bg      = ["rgba(251,191,36,.08)", "rgba(167,139,250,.1)", "rgba(129,140,248,.12)"]
    tc  = tier_colors[tier]
    tglow = tier_glow[tier]
    tbg  = tier_bg[tier]

    tier_labels = ["새싹 탐험가", "금융 전사", "주식 마스터 👑"]

    st.markdown(
        f"""
        <style>
        @keyframes floatY {{ 0%,100%{{transform:translateY(0)}} 50%{{transform:translateY(-14px)}} }}
        @keyframes popIn  {{ from{{opacity:0;transform:scale(.8)}} to{{opacity:1;transform:scale(1)}} }}
        @keyframes pulse  {{ 0%,100%{{box-shadow:0 0 0 0 {tglow}}} 70%{{box-shadow:0 0 0 18px transparent}} }}

        .rv-hero {{
            text-align:center; padding:32px 0 16px;
            animation:popIn .65s cubic-bezier(.34,1.56,.64,1);
        }}
        .rv-orb {{
            display:inline-flex; align-items:center; justify-content:center;
            width:140px; height:140px; border-radius:50%;
            background:radial-gradient(circle at 35% 35%, {tc}44, {tc}11);
            border:2px solid {tc}55;
            box-shadow:0 0 60px {tc}44, 0 0 120px {tc}22;
            animation:floatY 3.2s ease-in-out infinite, pulse 2.5s ease-in-out infinite;
            font-size:5rem; margin:0 auto 18px; position:relative;
        }}
        .rv-tier-badge {{
            display:inline-block; background:{tbg};
            border:1.5px solid {tc}66; border-radius:100px;
            padding:7px 22px; color:{tc}; font-size:1rem; font-weight:900;
            letter-spacing:-.2px; margin-bottom:10px;
            box-shadow:0 4px 20px {tc}33;
        }}
        .rv-congrats {{ color:rgba(255,255,255,.65); font-size:.92rem; margin:4px 0; }}
        .rv-stars {{ font-size:1.6rem; letter-spacing:4px; margin:10px 0; }}

        .rv-bento {{ display:grid; grid-template-columns:1fr 1fr 1fr; gap:14px; margin:24px 0 22px; }}
        .rv-box {{
            background:rgba(255,255,255,.1);
            backdrop-filter:blur(24px); -webkit-backdrop-filter:blur(24px);
            border:2px solid rgba(255,255,255,.2);
            border-top:3px solid {tc}99;
            border-radius:26px;
            padding:28px 12px; text-align:center;
            box-shadow:0 8px 28px rgba(0,0,0,.18), inset 0 1px 0 rgba(255,255,255,.18);
            transition: all .28s cubic-bezier(.34,1.56,.64,1);
        }}
        .rv-box:hover {{ transform:translateY(-6px) scale(1.03); box-shadow:0 18px 48px rgba(0,0,0,.28); }}
        .rv-num {{ font-size:2.2rem; font-weight:900; color:{tc}; line-height:1.2; }}
        .rv-lbl {{ font-size:.78rem; color:rgba(255,255,255,.55); margin-top:8px; letter-spacing:.3px; font-weight:700; }}

        .rv-tips-hd {{ color:white; font-size:1.05rem; font-weight:900; margin:8px 0 16px; letter-spacing:-.3px; }}
        .rv-tip {{
            display:flex; align-items:flex-start; gap:12px;
            background:rgba(255,255,255,.09);
            backdrop-filter:blur(16px);
            border:1.5px solid rgba(255,255,255,.15);
            border-left:4px solid {tc};
            border-radius:0 20px 20px 0;
            padding:14px 18px; margin-bottom:12px;
            color:rgba(255,255,255,.85); font-size:.92rem; line-height:1.8;
            transition: all .22s ease;
        }}
        .rv-tip:hover {{ background:rgba(255,255,255,.14); transform:translateX(4px); }}
        </style>
        <div class="rv-hero">
          <div class="rv-orb">{evo["emoji"]}</div>
          <div class="rv-tier-badge">{evo["tier_name"]}</div>
          <p style="color:rgba(255,255,255,.7);font-size:.95rem;margin:6px 0 4px;">{evo["desc"]}</p>
          <div class="rv-stars">{stars}</div>
          <p class="rv-congrats">{congrats}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        f'<div class="rv-bento">'
        f'<div class="rv-box"><div class="rv-num">🪙 {coins}</div><div class="rv-lbl">모은 쏠코인</div></div>'
        f'<div class="rv-box"><div class="rv-num">{done}</div><div class="rv-lbl">완료 미션</div></div>'
        f'<div class="rv-box"><div class="rv-num">{medal}</div><div class="rv-lbl">{wko}</div></div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    st.markdown('<div class="rv-tips-hd">📚 오늘 배운 금융 지식</div>', unsafe_allow_html=True)
    for tip in tips:
        st.markdown(f'<div class="rv-tip"><span>💡</span><span>{tip}</span></div>', unsafe_allow_html=True)

    # ── 엄마에게 조르기 ─────────────────────────────────────────────────
    st.markdown(
        """
        <div style="background:linear-gradient(135deg,rgba(255,107,107,.2),rgba(255,142,83,.15));
                    border:2px solid rgba(255,107,107,.4);border-radius:28px;
                    padding:24px;margin:24px 0 10px;text-align:center;
                    box-shadow:0 8px 32px rgba(255,107,107,.2);">
          <div style="font-size:3rem;margin-bottom:8px;animation:bounce 2s ease-in-out infinite;">💌</div>
          <p style="color:white;font-weight:900;font-size:1.1rem;margin:0 0 6px;">엄마에게 조르기!</p>
          <p style="color:rgba(255,255,255,.65);font-size:.88rem;margin:0;">퀴즈 결과를 엄마한테 메일로 보내봐요! 🙏</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if st.button("📲 엄마에게 문자 보내기!", use_container_width=True, key="sms_mom"):
        _send_result_sms(gs)

    st.divider()
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🔄 다시 탐험하기", use_container_width=True):
            gs.coins = 0
            gs.completed_missions.clear()
            gs.go_to("onboarding")
            st.session_state["intro_step"] = 0
            st.rerun()
    with col2:
        if st.button("📰 뉴스 더 보기", use_container_width=True, type="primary"):
            gs.go_to("news")
            st.rerun()


# ── SMS helper (NCP SENS) ─────────────────────────────────────────────────────

MOM_NUMBER = "01099859409"


_SHINHAN_PRODUCTS_INFO = [
    {
        "name": "신한 MY 주니어통장",
        "desc": "어린이 전용 입출금 통장 (수수료 무료)",
        "link": "https://bank.shinhan.com/index.jsp?pcd=110004701&cr=020102010110",
        "emoji": "🏦",
    },
    {
        "name": "신한 아이행복 적금",
        "desc": "매달 조금씩 모으는 어린이 전용 적금",
        "link": "https://bank.shinhan.com/index.jsp?pcd=110004400&cr=020102010110",
        "emoji": "🌱",
    },
    {
        "name": "신한 주니어 펀드",
        "desc": "우리 아이 미래를 위한 장기 투자 펀드",
        "link": "https://www.shinhanfund.com/ko/fund/search?category=junior",
        "emoji": "🚀",
    },
]


def _build_msg_text(gs: GameState) -> str:
    name  = gs.character_name or "아이"
    coins = gs.coins
    done  = len(gs.completed_missions)
    wko   = {"space": "별빛 금융 은하", "dinosaur": "공룡 정글",
              "magic": "마법왕국", "ocean": "파도 저금섬"}.get(gs.world or "space", "핀퀘스트")
    tier  = "주식 마스터 👑" if coins >= 100 else ("금융 전사 ⚔️" if coins >= 50 else "새싹 탐험가 🌱")

    if done > 0:
        score_line = f"퀴즈 {done}개 완료, 쏠코인 {coins}개 획득! 등급: {tier}"
    else:
        score_line = f"쏠코인 {coins}개 획득! 금융 공부 열심히 하는 중이에요!"

    return (
        f"엄마! 나 신한 쏠어드벤쳐에서 금융 공부 엄청 열심히 했어요! 📚\n\n"
        f"🎮 탐험 세계: {wko}\n"
        f"📊 오늘 결과: {score_line}\n\n"
        f"엄마, 나 이렇게 열심히 공부했으니까 용돈 좀 올려주세요~ 🙏🙏🙏\n"
        f"그리고 신한은행에서 나를 위한 금융 상품도 같이 알아봐요! 💕\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🏦 신한은행 어린이 추천 상품\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🌱 신한 아이행복 적금\n"
        f"   → https://bank.shinhan.com/index.jsp?pcd=110004400\n\n"
        f"🏦 신한 MY 주니어통장\n"
        f"   → https://bank.shinhan.com/index.jsp?pcd=110004701\n\n"
        f"🚀 신한 주니어 펀드 (장기 투자)\n"
        f"   → https://www.shinhanfund.com/ko/fund/search?category=junior\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"엄마 사랑해요 💖 용돈 올려줄 거죠? 🥺"
    )


def _build_html_email(gs: GameState) -> str:
    """HTML 형식 이메일 본문 생성."""
    name  = gs.character_name or "아이"
    coins = gs.coins
    done  = len(gs.completed_missions)
    wko   = {"space": "별빛 금융 은하", "dinosaur": "공룡 정글",
              "magic": "마법왕국", "ocean": "파도 저금섬"}.get(gs.world or "space", "핀퀘스트")
    tier  = "주식 마스터 👑" if coins >= 100 else ("금융 전사 ⚔️" if coins >= 50 else "새싹 탐험가 🌱")
    score = f"퀴즈 {done}개 완료 · 쏠코인 {coins}개 · {tier}" if done > 0 else f"쏠코인 {coins}개 획득 · {tier}"

    products_html = ""
    for p in _SHINHAN_PRODUCTS_INFO:
        products_html += f"""
        <tr>
          <td style="padding:14px 18px;border-bottom:1px solid #E8F0FF;">
            <span style="font-size:1.4rem;">{p['emoji']}</span>
          </td>
          <td style="padding:14px 18px;border-bottom:1px solid #E8F0FF;">
            <div style="font-weight:800;color:#003082;font-size:1rem;">{p['name']}</div>
            <div style="color:#6B7280;font-size:.85rem;margin-top:2px;">{p['desc']}</div>
          </td>
          <td style="padding:14px 18px;border-bottom:1px solid #E8F0FF;text-align:right;">
            <a href="{p['link']}" style="background:linear-gradient(135deg,#0044CC,#0068FF);
              color:white;text-decoration:none;padding:8px 16px;border-radius:20px;
              font-size:.82rem;font-weight:800;white-space:nowrap;">바로가기 →</a>
          </td>
        </tr>"""

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:#F0F4FF;font-family:'Apple SD Gothic Neo',sans-serif;">
  <div style="max-width:540px;margin:32px auto;background:white;border-radius:24px;overflow:hidden;
              box-shadow:0 8px 40px rgba(0,68,204,.18);">

    <!-- 헤더 -->
    <div style="background:linear-gradient(135deg,#0044CC 0%,#0068FF 60%,#1E8FFF 100%);
                padding:36px 32px;text-align:center;">
      <div style="font-size:3.5rem;margin-bottom:8px;">📚</div>
      <div style="color:rgba(255,255,255,.8);font-size:.8rem;font-weight:700;letter-spacing:1px;margin-bottom:8px;">
        신한 쏠어드벤쳐
      </div>
      <h1 style="color:white;font-size:1.5rem;font-weight:900;margin:0;letter-spacing:-.3px;">
        엄마! 나 금융 공부 열심히 했어요! 🥺
      </h1>
    </div>

    <!-- 본문 -->
    <div style="padding:32px;">
      <!-- 인사말 -->
      <p style="font-size:1rem;color:#374151;line-height:1.8;margin:0 0 24px;">
        엄마, <b style="color:#0044CC;">{name}</b>이에요! 😊<br>
        오늘 신한 쏠어드벤쳐에서 <b>「{wko}」</b>을 탐험하면서<br>
        저축, 투자, 주식에 대해 열심히 공부했어요!
      </p>

      <!-- 성적 카드 -->
      <div style="background:linear-gradient(135deg,#EEF4FF,#F0F9FF);border:2px solid #BFDBFE;
                  border-radius:20px;padding:20px 24px;margin-bottom:28px;text-align:center;">
        <div style="font-size:.75rem;font-weight:800;color:#6B7280;letter-spacing:.8px;margin-bottom:12px;">
          📊 오늘의 학습 성과
        </div>
        <div style="font-size:1.5rem;font-weight:900;color:#0044CC;">{score}</div>
      </div>

      <!-- 조르기 멘트 -->
      <div style="background:#FFF7ED;border:2px solid #FED7AA;border-radius:20px;
                  padding:20px 24px;margin-bottom:28px;">
        <p style="color:#92400E;font-size:1rem;line-height:1.85;margin:0;font-weight:700;">
          🙏 엄마, 이렇게 열심히 공부했으니까<br>
          용돈 조금만 올려주시면 안 될까요?<br>
          <span style="font-size:1.3rem;">더 열심히 할게요~ 💕</span>
        </p>
      </div>

      <!-- 상품 추천 -->
      <div style="margin-bottom:8px;">
        <div style="font-weight:900;color:#003082;font-size:1.05rem;margin-bottom:14px;
                    padding-bottom:10px;border-bottom:2px solid #E8F0FF;">
          🏦 나를 위한 신한은행 금융 상품이에요!
        </div>
        <p style="color:#6B7280;font-size:.88rem;margin:0 0 16px;line-height:1.7;">
          엄마, 아래 상품들이 저한테 딱 맞대요!<br>
          같이 알아봐요~ 😊
        </p>
        <table style="width:100%;border-collapse:collapse;border-radius:16px;overflow:hidden;
                      border:1px solid #E8F0FF;">
          {products_html}
        </table>
      </div>
    </div>

    <!-- 푸터 -->
    <div style="background:#F8FAFF;padding:20px 32px;text-align:center;
                border-top:1px solid #E8F0FF;">
      <p style="color:#9CA3AF;font-size:.75rem;margin:0;line-height:1.7;">
        신한 쏠어드벤쳐 · 어린이 금융 교육 게임<br>
        ※ 상품 금리·조건은 변동될 수 있으며, 상세 내용은 각 상품 페이지에서 확인해주세요.
      </p>
    </div>
  </div>
</body></html>"""


def _render_naver_mail_btn(msg_text: str, gs=None):
    """Gmail SMTP로 엄마 이메일에 직접 전송 (HTML 이메일)."""
    import smtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText
    try:
        from dotenv import load_dotenv
        load_dotenv(override=True)
    except Exception:
        pass

    sender   = os.environ.get("NAVER_MAIL_USER", "").strip().strip('"').strip("'")
    password = os.environ.get("NAVER_MAIL_PASS", "").strip().strip('"').strip("'")
    mom_mail = os.environ.get("MOM_EMAIL", "").strip().strip('"').strip("'")

    if not sender or not password or not mom_mail:
        st.markdown(
            """
            <div style="background:rgba(6,214,160,.1);border:2px solid rgba(6,214,160,.3);
                        border-radius:20px;padding:14px 20px;text-align:center;">
              <p style="color:#A8F7E5;font-size:.85rem;margin:0;font-weight:700;">
                💌 <b>.env</b>에 <code>NAVER_MAIL_USER</code>, <code>NAVER_MAIL_PASS</code>,
                <code>MOM_EMAIL</code>을 입력하면 바로 전송돼요!
              </p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    if st.button("💌 엄마한테 메일 바로 보내기", use_container_width=True, type="primary", key="naver_mail_btn"):
        with st.spinner("📨 전송 중..."):
            try:
                html_body = _build_html_email(gs) if gs is not None else None

                mime = MIMEMultipart("alternative")
                mime["Subject"] = "📚 [신한 쏠어드벤쳐] 용돈 올려주세요! 🙏"
                mime["From"]    = sender
                mime["To"]      = mom_mail

                # 텍스트 fallback
                mime.attach(MIMEText(msg_text, "plain", "utf-8"))
                # HTML 본문 (이메일 클라이언트가 지원하면 HTML이 우선)
                if html_body:
                    mime.attach(MIMEText(html_body, "html", "utf-8"))

                with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
                    smtp.login(sender, password)
                    smtp.sendmail(sender, mom_mail, mime.as_string())

                st.markdown(
                    """
                    <div style="background:linear-gradient(135deg,rgba(6,214,160,.2),rgba(6,214,160,.1));
                                border:2px solid rgba(6,214,160,.4);border-radius:24px;
                                padding:20px;text-align:center;margin:8px 0;">
                      <div style="font-size:2.5rem;margin-bottom:8px;">✅</div>
                      <p style="color:#06D6A0;font-weight:900;font-size:1rem;margin:0 0 4px;">메일 전송 완료!</p>
                      <p style="color:rgba(255,255,255,.65);font-size:.85rem;margin:0;">용돈 올려달라고 했어요 🙏</p>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
            except smtplib.SMTPAuthenticationError as e:
                st.error(f"❌ 로그인 실패: {e}")
            except Exception as e:
                st.error(f"❌ 전송 실패: {e}")


def _send_result_sms(gs: GameState):
    """결과 페이지용 메일 전송."""
    msg_text = _build_msg_text(gs)
    st.markdown(
        f"""
        <div style="background:rgba(255,255,255,.1);backdrop-filter:blur(24px);
                    border:2px solid rgba(255,107,107,.35);border-top:3px solid rgba(255,107,107,.6);
                    border-radius:28px;padding:24px;margin:8px 0;">
          <p style="color:rgba(255,214,10,.9);font-size:.78rem;font-weight:900;
                    letter-spacing:.6px;margin:0 0 12px;">📨 보낼 메시지 미리보기</p>
          <p style="color:white;font-size:.9rem;line-height:1.85;white-space:pre-line;margin:0;">{msg_text}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    _render_naver_mail_btn(msg_text, gs=gs)


# ── 엄마 조르기 페이지 ────────────────────────────────────────────────────────

def page_joreogi(gs: GameState):
    inject_css(gs.world or "space")
    _render_top_nav(gs)

    msg_text = _build_msg_text(gs)
    coins    = gs.coins
    done     = len(gs.completed_missions)

    st.markdown(
        """
        <div style="text-align:center;padding:36px 0 20px;animation:fadeUp .65s cubic-bezier(.34,1.56,.64,1);">
          <div style="font-size:4.5rem;display:block;animation:bounce 2.2s ease-in-out infinite;">💌</div>
          <h1 style="color:white;font-size:2rem;font-weight:900;margin:14px 0 8px;letter-spacing:-.5px;">엄마에게 조르기!</h1>
          <p style="color:rgba(255,255,255,.65);font-size:.96rem;">메일로 보내고 용돈을 올려달라고 해봐요!</p>
          <div style="display:flex;justify-content:center;gap:8px;margin-top:10px;">
            <span style="background:rgba(255,107,107,.25);border:1.5px solid rgba(255,107,107,.5);border-radius:100px;padding:4px 14px;color:#FFB3B3;font-size:.8rem;font-weight:800;">💰 용돈 인상</span>
            <span style="background:rgba(255,214,10,.2);border:1.5px solid rgba(255,214,10,.4);border-radius:100px;padding:4px 14px;color:#FFE566;font-size:.8rem;font-weight:800;">⭐ 성적 자랑</span>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── 메시지 미리보기 ───────────────────────────────────────────────
    st.markdown(
        f"""
        <div style="background:rgba(255,255,255,.1);backdrop-filter:blur(24px);
                    border:2px solid rgba(255,107,107,.35);border-top:3px solid rgba(255,107,107,.6);
                    border-radius:28px;padding:26px;margin:0 0 18px;
                    box-shadow:0 12px 40px rgba(0,0,0,.18);">
          <p style="color:rgba(255,214,10,.9);font-size:.78rem;font-weight:900;
                    letter-spacing:.6px;margin:0 0 14px;">📨 보낼 메시지 미리보기</p>
          <p style="color:white;font-size:.96rem;line-height:1.9;white-space:pre-line;margin:0;">{msg_text}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── 추천 상품 링크 미리보기 ─────────────────────────────────────
    products_preview = "".join(
        f'<div style="display:flex;align-items:center;justify-content:space-between;'
        f'background:rgba(255,255,255,.08);border:1.5px solid rgba(255,255,255,.15);'
        f'border-radius:18px;padding:12px 16px;margin-bottom:10px;">'
        f'<div style="display:flex;align-items:center;gap:10px;">'
        f'<span style="font-size:1.6rem;">{p["emoji"]}</span>'
        f'<div><div style="color:white;font-weight:800;font-size:.9rem;">{p["name"]}</div>'
        f'<div style="color:rgba(255,255,255,.55);font-size:.78rem;">{p["desc"]}</div></div>'
        f'</div>'
        f'<a href="{p["link"]}" target="_blank" style="background:linear-gradient(135deg,#0044CC,#0068FF);'
        f'color:white;text-decoration:none;padding:7px 14px;border-radius:14px;'
        f'font-size:.78rem;font-weight:900;white-space:nowrap;'
        f'box-shadow:0 4px 12px rgba(0,68,204,.4);">바로가기 →</a>'
        f'</div>'
        for p in _SHINHAN_PRODUCTS_INFO
    )
    st.markdown(
        f"""
        <div style="background:rgba(255,255,255,.08);backdrop-filter:blur(20px);
                    border:2px solid rgba(90,180,255,.3);border-top:3px solid rgba(0,68,204,.8);
                    border-radius:28px;padding:22px;margin:0 0 16px;">
          <p style="color:rgba(90,180,255,.9);font-size:.78rem;font-weight:900;
                    letter-spacing:.6px;margin:0 0 16px;">🏦 메일에 포함되는 신한 추천 상품</p>
          {products_preview}
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── 이메일 전송 버튼 ─────────────────────────────────────────────
    _render_naver_mail_btn(msg_text, gs=gs)

    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

    if st.button("🎮 게임하러 가기", use_container_width=True, key="joreogi_back"):
        gs.go_to("home")
        st.rerun()

    if done > 0:
        st.markdown(
            f"""
            <div style="background:rgba(255,215,0,.06);border:1px solid rgba(255,215,0,.2);
                        border-radius:18px;padding:16px 20px;margin:16px 0;text-align:center;">
              <p style="color:rgba(255,255,255,.7);font-size:.85rem;margin:0;">
                🎮 게임 기록: 퀴즈 <b style="color:white;">{done}개</b> 완료 · 쏠코인 <b style="color:#ffd700;">{coins}개</b>
              </p>
            </div>
            """,
            unsafe_allow_html=True,
        )


# ── Financial Word of the Day ─────────────────────────────────────────────────

FINANCE_WORDS = [
    {"word": "저축", "emoji": "🐷", "def": "미래를 위해 지금 돈을 아껴 모아두는 것이에요.", "tip": "매달 용돈의 10%만 저축해도 1년이면 큰돈이 돼요!"},
    {"word": "투자", "emoji": "📈", "def": "돈이 더 커지길 바라며 주식·부동산 등에 돈을 넣는 것이에요.", "tip": "투자는 수익도 있지만 손실도 있을 수 있어요. 공부가 필수!"},
    {"word": "이자", "emoji": "💰", "def": "은행에 돈을 맡기거나 빌리면 붙는 추가 금액이에요.", "tip": "은행에 저축하면 이자를 받고, 대출받으면 이자를 내요."},
    {"word": "예산", "emoji": "📋", "def": "쓸 돈을 미리 계획하는 것이에요.", "tip": "용돈을 받으면 먼저 예산부터 세워봐요!"},
    {"word": "복리", "emoji": "✨", "def": "이자에 또 이자가 붙어 돈이 눈덩이처럼 커지는 마법이에요.", "tip": "복리의 힘! 일찍 저축을 시작할수록 유리해요."},
    {"word": "주식", "emoji": "🏦", "def": "회사의 아주 작은 조각을 사는 것이에요. 회사가 잘 되면 가치가 올라요.", "tip": "주식은 단기가 아닌 장기로 보는 것이 좋아요!"},
    {"word": "분산투자", "emoji": "🌈", "def": "여러 곳에 나눠 투자해 위험을 줄이는 방법이에요.", "tip": "'달걀을 한 바구니에 담지 마라'는 말처럼요!"},
    {"word": "보험", "emoji": "🛡️", "def": "갑작스러운 사고나 병을 대비해 미리 돈을 내두는 안전망이에요.", "tip": "보험은 불의의 사고에서 우리를 지켜줘요."},
    {"word": "소비", "emoji": "🛍️", "def": "물건이나 서비스를 사는 데 돈을 쓰는 것이에요.", "tip": "필요한 것과 갖고 싶은 것을 구분해서 소비해요!"},
    {"word": "수입", "emoji": "💵", "def": "용돈, 월급처럼 내가 받는 돈이에요.", "tip": "수입보다 더 많이 쓰면 빚이 생겨요. 균형이 중요해요!"},
]

def page_word_of_day(gs: GameState):
    inject_css(gs.world or "space")
    _render_top_nav(gs)

    import hashlib
    from datetime import date
    day_idx = int(hashlib.md5(str(date.today()).encode()).hexdigest(), 16) % len(FINANCE_WORDS)
    word = FINANCE_WORDS[day_idx]

    st.markdown(
        f"""
        <style>
        .wd-hero {{
            text-align:center; padding:28px 0 16px;
            animation:fadeUp .65s cubic-bezier(.34,1.56,.64,1);
        }}
        .wd-badge {{
            display:inline-flex; align-items:center; gap:6px;
            background:linear-gradient(135deg,rgba(255,214,10,.25),rgba(255,107,107,.2));
            border:2px solid rgba(255,214,10,.5); border-radius:100px;
            padding:7px 20px; color:#FFE566; font-size:.82rem; font-weight:900;
            letter-spacing:.8px; margin-bottom:18px;
            box-shadow:0 4px 16px rgba(255,214,10,.3);
        }}
        .wd-card {{
            background:rgba(255,255,255,.1);
            backdrop-filter:blur(32px); -webkit-backdrop-filter:blur(32px);
            border:2px solid rgba(255,255,255,.22);
            border-top:3px solid rgba(255,214,10,.7);
            border-radius:32px;
            padding:36px 32px; margin:18px 0;
            box-shadow:0 16px 48px rgba(0,0,0,.22), inset 0 1px 0 rgba(255,255,255,.18);
        }}
        .wd-tip {{
            background:linear-gradient(135deg,rgba(255,214,10,.18),rgba(255,163,26,.12));
            border:2px solid rgba(255,214,10,.35);
            border-radius:20px; padding:16px 20px; margin-top:22px;
            color:#FFE566; font-size:.92rem; line-height:1.75; font-weight:700;
            box-shadow:0 4px 20px rgba(255,214,10,.15);
        }}
        </style>
        <div class="wd-hero">
          <div class="wd-badge">오늘의 금융 단어</div>
          <div style="font-size:4.5rem;animation:floatY 3s ease-in-out infinite;display:block;margin-bottom:8px;">{word["emoji"]}</div>
          <h1 style="color:white;font-size:2.8rem;font-weight:900;letter-spacing:-1px;margin:0;">{word["word"]}</h1>
        </div>
        <div class="wd-card">
          <p style="color:rgba(255,255,255,.5);font-size:.78rem;font-weight:700;letter-spacing:.8px;margin:0 0 12px;">무슨 뜻이에요?</p>
          <p style="color:white;font-size:1.08rem;line-height:1.85;margin:0;">{word["def"]}</p>
          <div class="wd-tip">💡 {word["tip"]}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        '<p style="color:rgba(255,255,255,.4);font-size:.78rem;text-align:center;margin:4px 0 16px;">매일 새로운 금융 단어가 업데이트돼요!</p>',
        unsafe_allow_html=True,
    )

    all_words_html = "".join(
        f'<div style="display:inline-flex;align-items:center;gap:6px;background:rgba(255,255,255,.07);'
        f'border:1px solid rgba(255,255,255,.12);border-radius:100px;padding:6px 14px;margin:4px;">'
        f'<span>{w["emoji"]}</span><span style="color:white;font-weight:700;font-size:.85rem;">{w["word"]}</span></div>'
        for w in FINANCE_WORDS
    )
    st.markdown(
        f'<div style="margin:8px 0 20px;">'
        f'<p style="color:rgba(255,255,255,.5);font-size:.82rem;font-weight:700;margin:0 0 10px;">📖 금융 단어 모음</p>'
        f'<div>{all_words_html}</div></div>',
        unsafe_allow_html=True,
    )

    col1, col2 = st.columns(2)
    with col1:
        if st.button("🗺️ 게임으로 돌아가기", use_container_width=True):
            gs.go_to("map")
            st.rerun()
    with col2:
        if st.button("📰 주식 뉴스 보기", use_container_width=True, type="primary"):
            gs.go_to("news")
            st.rerun()


# ── Allowance Tracker ────────────────────────────────────────────────────────

def page_allowance(gs: GameState):
    inject_css(gs.world or "space")
    _render_top_nav(gs)

    records = st.session_state.setdefault("allowance_records", [])
    total_in  = sum(r["amount"] for r in records if r["type"] == "in")
    total_out = sum(r["amount"] for r in records if r["type"] == "out")
    balance   = total_in - total_out

    balance_color = "#4ade80" if balance >= 0 else "#f87171"

    st.markdown(
        f"""
        <div style="animation:fadeUp .6s ease-out;padding:20px 0 8px;">
          <h2 style="color:white;font-size:1.7rem;font-weight:900;letter-spacing:-.5px;margin:0 0 6px;">💰 용돈 기입장</h2>
          <p style="color:rgba(255,255,255,.55);font-size:.9rem;margin:0;">내 용돈을 기록하고 관리해봐요!</p>
        </div>
        <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:14px;margin:20px 0 26px;">
          <div style="background:rgba(6,214,160,.15);border:2px solid rgba(6,214,160,.4);
              border-top:3px solid rgba(6,214,160,.7);border-radius:24px;padding:22px 12px;text-align:center;
              box-shadow:0 6px 24px rgba(6,214,160,.18);">
            <div style="font-size:1.8rem;font-weight:900;color:#06D6A0;">+{total_in:,}원</div>
            <div style="font-size:.78rem;color:rgba(255,255,255,.55);margin-top:6px;font-weight:700;">받은 용돈</div>
          </div>
          <div style="background:rgba(255,107,107,.15);border:2px solid rgba(255,107,107,.4);
              border-top:3px solid rgba(255,107,107,.7);border-radius:24px;padding:22px 12px;text-align:center;
              box-shadow:0 6px 24px rgba(255,107,107,.18);">
            <div style="font-size:1.8rem;font-weight:900;color:#FF6B6B;">-{total_out:,}원</div>
            <div style="font-size:.78rem;color:rgba(255,255,255,.55);margin-top:6px;font-weight:700;">쓴 돈</div>
          </div>
          <div style="background:rgba(255,255,255,.1);border:2px solid rgba(255,255,255,.2);
              border-top:3px solid rgba(255,214,10,.6);border-radius:24px;padding:22px 12px;text-align:center;
              box-shadow:0 6px 24px rgba(0,0,0,.15);">
            <div style="font-size:1.8rem;font-weight:900;color:{balance_color};">{balance:,}원</div>
            <div style="font-size:.78rem;color:rgba(255,255,255,.55);margin-top:6px;font-weight:700;">남은 용돈</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.expander("➕ 새 기록 추가", expanded=len(records) == 0):
        c1, c2 = st.columns(2)
        with c1:
            rtype = st.selectbox("종류", ["받은 돈 💚", "쓴 돈 ❤️"], key="al_type")
        with c2:
            amount = st.number_input("금액 (원)", min_value=0, step=100, key="al_amount")
        desc = st.text_input("내용 (예: 주간 용돈, 간식 구매)", key="al_desc", placeholder="무엇에 썼나요?")
        if st.button("기록 추가", type="primary", use_container_width=True, key="al_add"):
            if amount > 0 and desc.strip():
                records.append({
                    "type": "in" if "받은" in rtype else "out",
                    "amount": int(amount),
                    "desc": desc.strip(),
                    "emoji": "💚" if "받은" in rtype else "❤️",
                })
                st.session_state["allowance_records"] = records
                st.rerun()
            else:
                st.warning("금액과 내용을 모두 입력해줘요!")

    if records:
        st.markdown('<p style="color:rgba(255,255,255,.6);font-size:.85rem;font-weight:700;margin:12px 0 8px;">📋 기록 내역</p>', unsafe_allow_html=True)
        for r in reversed(records[-20:]):
            col = "#4ade80" if r["type"] == "in" else "#f87171"
            sign = "+" if r["type"] == "in" else "-"
            st.markdown(
                f'<div style="display:flex;justify-content:space-between;align-items:center;'
                f'background:rgba(255,255,255,.08);border:1.5px solid rgba(255,255,255,.15);'
                f'border-left:4px solid {col};'
                f'border-radius:0 18px 18px 0;padding:13px 18px;margin-bottom:10px;'
                f'transition:all .2s ease;">'
                f'<span style="color:rgba(255,255,255,.85);font-size:.92rem;font-weight:700;">{r["emoji"]} {r["desc"]}</span>'
                f'<span style="color:{col};font-weight:900;font-size:1rem;">{sign}{r["amount"]:,}원</span>'
                f'</div>',
                unsafe_allow_html=True,
            )
        if st.button("🗑️ 전체 초기화", use_container_width=True):
            st.session_state["allowance_records"] = []
            st.rerun()
    else:
        st.markdown(
            '<div style="text-align:center;padding:32px;color:rgba(255,255,255,.35);font-size:.9rem;">'
            '아직 기록이 없어요. 첫 번째 기록을 추가해봐요! 💰</div>',
            unsafe_allow_html=True,
        )

    if st.button("🏠 홈으로", use_container_width=True):
        gs.go_to("onboarding")
        st.session_state["intro_step"] = 0
        st.rerun()


# ── Savings Goal Tracker ──────────────────────────────────────────────────────

def page_savings(gs: GameState):
    inject_css(gs.world or "space")
    _render_top_nav(gs)

    goal     = st.session_state.get("savings_goal", 0)
    saved    = st.session_state.get("savings_saved", 0)
    goal_name = st.session_state.get("savings_goal_name", "")
    pct      = min(int(saved / goal * 100), 100) if goal > 0 else 0

    pig_emoji = "🐣" if pct < 30 else ("🐥" if pct < 60 else ("🐔" if pct < 100 else "🎉"))

    st.markdown(
        f"""
        <div style="animation:fadeUp .65s ease-out;padding:20px 0 8px;">
          <h2 style="color:white;font-size:1.7rem;font-weight:900;letter-spacing:-.5px;margin:0 0 6px;">🐷 저축 목표</h2>
          <p style="color:rgba(255,255,255,.55);font-size:.9rem;margin:0;">저금통을 채워서 꿈을 이뤄봐요!</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if goal > 0:
        bar_color = "#06D6A0" if pct >= 100 else "#845EF7"
        bar_color2 = "#5AB4FF" if pct >= 100 else "#FF6B6B"
        st.markdown(
            f"""
            <div style="background:rgba(255,255,255,.1);backdrop-filter:blur(28px);
                        border:2px solid rgba(255,255,255,.22);border-top:3px solid {bar_color};
                        border-radius:32px;padding:30px;margin:18px 0;
                        box-shadow:0 12px 40px rgba(0,0,0,.2);">
              <div style="text-align:center;margin-bottom:22px;">
                <div style="font-size:4.5rem;animation:floatY 2.8s ease-in-out infinite;
                    filter:drop-shadow(0 0 16px rgba(132,94,247,.5));">{pig_emoji}</div>
                <div style="color:white;font-size:1.3rem;font-weight:900;margin:12px 0 6px;letter-spacing:-.3px;">
                    {goal_name or "저축 목표"}</div>
                <div style="color:rgba(255,255,255,.6);font-size:.88rem;font-weight:700;">{saved:,}원 / {goal:,}원</div>
              </div>
              <div style="background:rgba(255,255,255,.12);border-radius:100px;height:20px;overflow:hidden;margin-bottom:10px;">
                <div style="background:linear-gradient(90deg,{bar_color},{bar_color2});height:100%;
                             width:{pct}%;border-radius:100px;transition:width .6s ease;
                             box-shadow:0 0 16px {bar_color}88;"></div>
              </div>
              <div style="text-align:right;color:{bar_color};font-size:.92rem;font-weight:900;">{pct}% 달성! 🎯</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        add_amt = st.number_input("저금할 금액 (원)", min_value=0, step=100, key="sav_add_amt")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("💰 저금하기", type="primary", use_container_width=True):
                if add_amt > 0:
                    st.session_state["savings_saved"] = saved + int(add_amt)
                    if st.session_state["savings_saved"] >= goal:
                        st.balloons()
                    st.rerun()
        with c2:
            if st.button("🔄 목표 바꾸기", use_container_width=True):
                st.session_state["savings_goal"] = 0
                st.session_state["savings_saved"] = 0
                st.rerun()
    else:
        st.markdown(
            '<div style="text-align:center;padding:24px 0 8px;color:rgba(255,255,255,.6);">저축 목표를 설정해봐요! 🐷</div>',
            unsafe_allow_html=True,
        )
        new_name = st.text_input("무엇을 위해 저축하나요?", placeholder="예: 닌텐도 스위치, 용돈 모으기", key="sav_name")
        new_goal = st.number_input("목표 금액 (원)", min_value=0, step=1000, key="sav_goal_input")
        if st.button("🎯 목표 설정하기!", type="primary", use_container_width=True):
            if new_goal > 0:
                st.session_state["savings_goal"] = int(new_goal)
                st.session_state["savings_saved"] = 0
                st.session_state["savings_goal_name"] = new_name.strip() or "저축 목표"
                st.rerun()
            else:
                st.warning("목표 금액을 입력해줘요!")

    if st.button("🏠 홈으로", use_container_width=True):
        gs.go_to("onboarding")
        st.session_state["intro_step"] = 0
        st.rerun()


# ── Shinhan Products ──────────────────────────────────────────────────────────

SHINHAN_PRODUCTS = [
    {
        "id": "junior_account",
        "emoji": "🏦",
        "name": "신한 MY 주니어통장",
        "tag": "통장",
        "tag_color": "#22c55e",
        "target": "만 18세 이하 누구나",
        "difficulty": 1,
        "difficulty_label": "쉬움",
        "headline": "어린이 전용 통장이에요!",
        "simple": (
            "용돈을 안전하게 넣어두는 나만의 통장이에요. "
            "부모님이 같이 만들어 주실 수 있어요."
        ),
        "points": [
            "💳 ATM 출금 수수료 무료 (조건 충족 시)",
            "📱 신한 SOL뱅크 앱으로 잔액 확인",
            "🎁 용돈을 받으면 바로 저금 가능",
            "🔒 부모님이 함께 관리해줘요",
        ],
        "analogy": "마치 학교 사물함처럼, 내 돈을 안전하게 보관하는 곳이에요!",
        "link": "https://bank.shinhan.com/index.jsp?pcd=110004701&cr=020102010110",
    },
    {
        "id": "ai_haengbok",
        "emoji": "🌱",
        "name": "신한 아이행복 적금",
        "tag": "적금",
        "tag_color": "#f59e0b",
        "target": "만 18세 이하 어린이",
        "difficulty": 1,
        "difficulty_label": "쉬움",
        "headline": "매달 조금씩 모으면 이자를 받아요!",
        "simple": (
            "매달 정해진 돈을 꼬박꼬박 넣으면, "
            "은행이 '잘했어!' 하고 이자를 얹어 돌려줘요. "
            "1년 후엔 내가 넣은 것보다 더 많은 돈을 받아요!"
        ),
        "points": [
            "📅 월 1만 원부터 시작 가능",
            "💰 일반 예금보다 더 높은 금리 혜택",
            "🎂 어린이날·생일 특별 우대금리",
            "👨‍👩‍👧 부모님 명의로 가입, 자녀 수혜",
        ],
        "analogy": "매달 저금통에 동전을 넣는 것처럼, 나도 모르게 큰돈이 쌓여요!",
        "link": "https://bank.shinhan.com/index.jsp?pcd=230012101&cr=020102010110",
    },
    {
        "id": "junior_savings",
        "emoji": "⭐",
        "name": "신한 MY 주니어 적금",
        "tag": "적금",
        "tag_color": "#f59e0b",
        "target": "만 18세 이하",
        "difficulty": 2,
        "difficulty_label": "보통",
        "headline": "목표를 정하고 꾸준히 모아요!",
        "simple": (
            "게임에서 아이템을 모으듯, "
            "목표 금액을 정하고 매달 조금씩 채워가요. "
            "목표를 달성하면 더 높은 이자를 받을 수 있어요!"
        ),
        "points": [
            "🎯 자유로운 납입 금액 설정",
            "📈 우대금리 조건 달성 시 이자 추가",
            "🏆 만기 시 목표 달성 축하 혜택",
            "📲 SOL뱅크 앱에서 진행상황 확인",
        ],
        "analogy": "게임 퀘스트처럼 목표를 클리어하면 보너스 코인을 받아요!",
        "link": "https://bank.shinhan.com/index.jsp?pcd=230012102&cr=020102010110",
    },
    {
        "id": "kids_fund",
        "emoji": "🚀",
        "name": "신한엄마사랑 어린이 펀드",
        "tag": "펀드",
        "tag_color": "#818cf8",
        "target": "어린이를 위해 부모님이 투자",
        "difficulty": 3,
        "difficulty_label": "어려움",
        "headline": "돈이 주식시장에서 일하게 해요!",
        "simple": (
            "펀드는 여러 사람의 돈을 모아 전문가가 주식에 투자하는 거예요. "
            "회사들이 잘 되면 내 돈도 함께 커져요. "
            "대신 주식이 내려가면 손해가 날 수도 있어서 '장기 투자'가 중요해요!"
        ),
        "points": [
            "📊 전문가가 대신 주식 골라줘요",
            "🌍 국내외 우량 기업에 분산투자",
            "⏳ 10년 이상 오래 투자할수록 유리해요",
            "⚠️ 원금 손실 가능성 있음 (부모님과 상의 필수)",
        ],
        "analogy": "씨앗을 심으면 오래 기다려야 나무가 되듯, 펀드도 기다리면 커져요!",
        "link": "https://www.shinhanfund.com/ko/pc/fund/view?fundCd=250197",
    },
    {
        "id": "youth_deposit",
        "emoji": "🎓",
        "name": "청년 처음적금 (예비 청년용)",
        "tag": "미래 준비",
        "tag_color": "#06b6d4",
        "target": "중학생 이상 ~ 만 34세",
        "difficulty": 2,
        "difficulty_label": "보통",
        "headline": "지금부터 준비하면 커서 유리해요!",
        "simple": (
            "중학생, 고등학생도 미래를 위해 미리 알아두면 좋아요. "
            "사회에 나가면 첫 월급을 저축하는 '처음적금'이 있어요. "
            "지금부터 저축 습관을 들이면 나중에 더 잘할 수 있어요!"
        ),
        "points": [
            "🌟 청년 우대금리 최고 제공",
            "💼 사회초년생 첫 저축 상품",
            "📅 자유롭게 납입 가능",
            "🎁 지금부터 저축 습관 기르기",
        ],
        "analogy": "운동선수가 어릴 때부터 연습하듯, 돈 관리도 미리 연습해요!",
        "link": "https://bank.shinhan.com/index.jsp?pcd=230011997&cr=020102010110",
    },
]

PRODUCT_TIPS = [
    "💡 적금은 '이자'가 붙어서 안전해요. 펀드는 '수익'이 더 클 수 있지만 위험도 있어요!",
    "💡 어릴 때 저축 습관을 들이면 커서도 돈을 잘 모을 수 있어요!",
    "💡 복리란? 이자에 또 이자가 붙는 마법! 일찍 시작할수록 돈이 쑥쑥 커져요.",
    "💡 투자는 항상 '잃을 수 있다'는 것을 기억해요. 소중한 돈은 먼저 저금해요!",
]


def page_products(gs: GameState):
    inject_css(gs.world or "space")
    _render_top_nav(gs)

    st.markdown(
        """
        <style>
        .pd-hero { text-align:center; padding:28px 0 18px; animation:fadeUp .7s cubic-bezier(.34,1.56,.64,1); }
        .pd-card {
            background:rgba(255,255,255,.1);
            backdrop-filter:blur(32px); -webkit-backdrop-filter:blur(32px);
            border:2px solid rgba(255,255,255,.2);
            border-top:3px solid rgba(255,255,255,.5);
            border-radius:32px;
            padding:28px 26px; margin-bottom:20px;
            box-shadow:0 12px 40px rgba(0,0,0,.2), inset 0 1px 0 rgba(255,255,255,.18);
            transition:all .28s cubic-bezier(.34,1.56,.64,1);
        }
        .pd-card:hover { transform:translateY(-4px); box-shadow:0 20px 56px rgba(0,0,0,.28); }
        .pd-tag {
            display:inline-block; border-radius:100px;
            padding:5px 14px; font-size:.74rem; font-weight:900; letter-spacing:.3px;
            margin-bottom:12px; border-width:2px; border-style:solid;
        }
        .pd-diff { display:flex; gap:5px; margin-bottom:10px; align-items:center; }
        .pd-dot-on  { width:11px; height:11px; border-radius:50%; background:rgba(255,255,255,.95);
            box-shadow:0 0 6px rgba(255,255,255,.6); }
        .pd-dot-off { width:11px; height:11px; border-radius:50%; background:rgba(255,255,255,.2); }
        .pd-point {
            display:flex; align-items:flex-start; gap:8px;
            color:rgba(255,255,255,.82); font-size:.9rem; line-height:1.65;
            margin-bottom:8px;
        }
        .pd-analogy {
            background:linear-gradient(135deg,rgba(255,214,10,.2),rgba(255,163,26,.12));
            border:2px solid rgba(255,214,10,.38);
            border-radius:20px; padding:14px 18px; margin-top:18px;
            color:#FFE566; font-size:.9rem; line-height:1.75; font-weight:700;
            box-shadow:0 4px 16px rgba(255,214,10,.15);
        }
        .pd-tip {
            background:rgba(255,255,255,.08); border-left:4px solid rgba(255,214,10,.6);
            border-radius:0 16px 16px 0; padding:13px 16px; margin:8px 0;
            color:rgba(255,255,255,.82); font-size:.88rem; line-height:1.7;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        """
        <div class="pd-hero">
          <div style="display:inline-flex;align-items:center;gap:6px;
                      background:white;border-radius:100px;
                      padding:7px 20px;color:#003082;font-size:.8rem;
                      font-weight:900;letter-spacing:.5px;margin-bottom:18px;
                      box-shadow:0 4px 16px rgba(0,0,0,.2);">
            <div style="width:18px;height:18px;background:linear-gradient(135deg,#0044CC,#0068FF);
                border-radius:50%;display:inline-flex;align-items:center;justify-content:center;
                font-size:9px;color:white;font-weight:900;">신</div>
            신한은행 추천 상품
          </div>
          <div style="font-size:3.5rem;animation:bounce 1.2s ease-out;display:block;margin-bottom:10px;
              filter:drop-shadow(0 0 16px rgba(6,214,160,.5));">🏦</div>
          <h2 style="color:white;font-size:1.9rem;font-weight:900;letter-spacing:-.6px;margin:0 0 10px;">
            어린이 금융 상품 추천
          </h2>
          <p style="color:rgba(255,255,255,.65);font-size:.96rem;margin:0;font-weight:700;">
            쏠쏠이가 쉽게 설명해줄게요! 부모님과 함께 알아봐요 😊
          </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    for p in SHINHAN_PRODUCTS:
        diff_dots = (
            "".join('<div class="pd-dot-on"></div>' for _ in range(p["difficulty"]))
            + "".join('<div class="pd-dot-off"></div>' for _ in range(3 - p["difficulty"]))
        )
        points_html = "".join(f'<div class="pd-point">{pt}</div>' for pt in p["points"])

        r2, g2, b2 = tuple(int(p["tag_color"].lstrip("#")[i:i+2], 16) for i in (0, 2, 4))
        st.markdown(
            f'<div class="pd-card" style="border-top-color:rgba({r2},{g2},{b2},.8);">'
            f'<div style="display:flex;align-items:flex-start;justify-content:space-between;margin-bottom:14px;">'
            f'  <div>'
            f'    <span class="pd-tag" style="background:rgba({r2},{g2},{b2},.2);color:{p["tag_color"]};border-color:rgba({r2},{g2},{b2},.45);">{p["tag"]}</span>'
            f'    <div class="pd-diff">{diff_dots}'
            f'      <span style="color:rgba(255,255,255,.45);font-size:.74rem;margin-left:5px;font-weight:700;">난이도: {p["difficulty_label"]}</span>'
            f'    </div>'
            f'  </div>'
            f'  <div style="font-size:3.2rem;filter:drop-shadow(0 0 12px rgba({r2},{g2},{b2},.5));">{p["emoji"]}</div>'
            f'</div>'
            f'<h3 style="color:white;font-size:1.15rem;font-weight:900;margin:0 0 6px;letter-spacing:-.3px;">{p["name"]}</h3>'
            f'<p style="color:{p["tag_color"]};font-size:.87rem;font-weight:800;margin:0 0 14px;">👶 대상: {p["target"]}</p>'
            f'<p style="color:rgba(255,255,255,.5);font-size:.76rem;font-weight:900;letter-spacing:.6px;margin:0 0 6px;">한 마디로?</p>'
            f'<p style="color:white;font-size:1.02rem;font-weight:800;margin:0 0 14px;letter-spacing:-.2px;">{p["headline"]}</p>'
            f'<p style="color:rgba(255,255,255,.75);font-size:.92rem;line-height:1.85;margin:0 0 16px;">{p["simple"]}</p>'
            f'<div>{points_html}</div>'
            f'<div class="pd-analogy">🌟 {p["analogy"]}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
        st.link_button(f"🔗 {p['name']} 자세히 보기", p["link"], use_container_width=True)

    st.divider()
    st.markdown('<p style="color:rgba(255,255,255,.6);font-size:.88rem;font-weight:700;margin:0 0 10px;">📌 알아두면 좋아요!</p>', unsafe_allow_html=True)
    for tip in PRODUCT_TIPS:
        st.markdown(f'<div class="pd-tip">{tip}</div>', unsafe_allow_html=True)

    st.markdown(
        '<p style="color:rgba(255,255,255,.3);font-size:.72rem;text-align:center;margin:16px 0 8px;">'
        '※ 상품 금리·조건은 변동될 수 있어요. 자세한 내용은 신한은행 공식 홈페이지 또는 영업점에서 확인해주세요.'
        '</p>',
        unsafe_allow_html=True,
    )

    col1, col2 = st.columns(2)
    with col1:
        if st.button("🏠 홈으로", use_container_width=True):
            gs.go_to("onboarding")
            st.session_state["intro_step"] = 0
            st.rerun()
    with col2:
        if st.button("🎮 게임 계속하기", use_container_width=True, type="primary"):
            if gs.world:
                gs.go_to("map")
            else:
                gs.go_to("onboarding")
            st.rerun()


# ── Router ────────────────────────────────────────────────────────────────────

def main():
    # 새로고침 후 진행 데이터 복원 (URL sid 기반)
    try:
        from game.persistence import try_restore
        try_restore()
    except Exception:
        pass

    worlds = load_worlds()
    missions = load_missions()
    gs = GameState()
    badge_engine = BadgeEngine()
    _load_progress(gs)   # 이전 세션 진행 상황 복원

    kick_preloads(gs)   # 뉴스·퀴즈 백그라운드 프리로드 (매 rerun마다 safe하게 호출)

    render_sidebar(gs, badge_engine, worlds)

    page = st.session_state.get("page", "onboarding")

    if page == "onboarding":
        page_onboarding(gs, worlds)
    elif page == "map":
        page_map(gs, worlds, missions, badge_engine)
    elif page == "mission":
        page_mission(gs, worlds, missions, badge_engine)
    elif page == "report":
        page_report(gs, worlds, missions, badge_engine)
    elif page == "news":
        page_news(gs)
    elif page == "result":
        page_result(gs)
    elif page == "word":
        page_word_of_day(gs)
    elif page == "allowance":
        page_allowance(gs)
    elif page == "savings":
        page_savings(gs)
    elif page == "products":
        page_products(gs)
    elif page == "joreogi":
        page_joreogi(gs)
    else:
        gs.go_to("onboarding")
        st.rerun()


if __name__ == "__main__":
    main()
