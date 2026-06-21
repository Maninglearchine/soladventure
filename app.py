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
        @keyframes floatY  {{ 0%,100%{{transform:translateY(0)}} 50%{{transform:translateY(-10px)}} }}
        @keyframes fadeUp  {{ from{{opacity:0;transform:translateY(24px)}} to{{opacity:1;transform:translateY(0)}} }}
        @keyframes popIn   {{ from{{opacity:0;transform:scale(.88)}} to{{opacity:1;transform:scale(1)}} }}
        @keyframes glow    {{ 0%,100%{{opacity:.7}} 50%{{opacity:1}} }}
        @keyframes shimmer {{ 0%{{background-position:200% center}} 100%{{background-position:-200% center}} }}

        header[data-testid="stHeader"], footer {{ display:none !important; }}
        #MainMenu {{ visibility:hidden !important; }}
        section[data-testid="stSidebar"] {{ display:none !important; }}

        /* ── Background ── */
        .stApp, section[data-testid="stMain"], section[data-testid="stMain"] > div, .main > div {{
            background: linear-gradient(150deg, #00112e 0%, #001a5c 30%, #003082 65%, #0057c2 100%) !important;
        }}
        .block-container {{
            background: transparent !important;
            max-width: 900px !important;
            padding-top: 1.2rem !important;
        }}

        /* ── Buttons (default = glass pill) ── */
        .stButton > button {{
            border-radius: 100px !important;
            font-weight: 700 !important;
            font-size: .93rem !important;
            letter-spacing: .1px !important;
            transition: all .22s cubic-bezier(.34,1.56,.64,1) !important;
            color: rgba(255,255,255,.92) !important;
            background: rgba(255,255,255,.1) !important;
            backdrop-filter: blur(12px) !important;
            -webkit-backdrop-filter: blur(12px) !important;
            border: 1px solid rgba(255,255,255,.22) !important;
            padding: 11px 26px !important;
            box-shadow: 0 2px 14px rgba(0,0,0,.22),
                        inset 0 1px 0 rgba(255,255,255,.15) !important;
        }}
        .stButton > button:hover {{
            background: rgba(255,255,255,.18) !important;
            border-color: rgba(255,255,255,.38) !important;
            color: white !important;
            transform: translateY(-2px) scale(1.02) !important;
            box-shadow: 0 8px 28px rgba(0,0,0,.3),
                        inset 0 1px 0 rgba(255,255,255,.22) !important;
        }}
        .stButton > button[kind="primary"] {{
            background: linear-gradient(135deg, #4361ee 0%, #0057c2 100%) !important;
            color: white !important;
            border: none !important;
            box-shadow: 0 4px 20px rgba(67,97,238,.55) !important;
        }}
        .stButton > button[kind="primary"]:hover {{
            background: linear-gradient(135deg, #3651d4 0%, #0047a8 100%) !important;
            box-shadow: 0 8px 32px rgba(67,97,238,.72) !important;
            transform: translateY(-3px) scale(1.02) !important;
        }}

        /* ── Glass card base ── */
        .glass-card {{
            background: rgba(255,255,255,.06);
            backdrop-filter: blur(24px);
            -webkit-backdrop-filter: blur(24px);
            border: 1px solid rgba(255,255,255,.13);
            border-radius: 24px;
            box-shadow: 0 8px 32px rgba(0,0,0,.22), inset 0 1px 0 rgba(255,255,255,.08);
        }}

        /* ── Progress bar ── */
        div[data-testid="stProgress"] > div {{ background-color: {color}; border-radius: 100px; }}

        /* ── White text on blue bg ── */
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
        label[data-testid="stWidgetLabel"] p {{
            color: white !important;
        }}
        /* ── 버튼 글씨 강제 지정 ── */
        [data-testid="stButton"] p,
        [data-testid="stButton"] span,
        [data-testid="stButton"] [data-testid="stMarkdownContainer"] p,
        [data-testid="stButton"] [data-testid="stMarkdownContainer"] span {{ color: rgba(255,255,255,.92) !important; }}
        [data-testid="stButton"] button[kind="primary"] p,
        [data-testid="stButton"] button[kind="primary"] span,
        [data-testid="stButton"] button[kind="primary"] [data-testid="stMarkdownContainer"] p,
        [data-testid="stButton"] button[kind="primary"] [data-testid="stMarkdownContainer"] span {{ color: white !important; }}
        div[data-testid="stSpinner"] p, div[data-testid="stSpinner"] span {{ color: white !important; }}
        hr {{ border-color: rgba(255,255,255,.1) !important; margin: 1.2rem 0 !important; }}

        /* ── Tooltip (말풍선) — 흰 배경에 어두운 글씨 ── */
        [data-testid="tooltipContent"],
        [data-testid="tooltipContent"] p,
        [data-testid="tooltipContent"] span,
        div[role="tooltip"],
        div[role="tooltip"] p,
        div[role="tooltip"] span {{ color: #0d1b3e !important; background: white; }}

        /* ── Shinhan logo button ── */
        div:has(#top-nav-sentinel) ~ [data-testid="stHorizontalBlock"] > div:first-child [data-testid="stButton"] {{
            margin-top: 0 !important; z-index: auto !important;
        }}
        div:has(#top-nav-sentinel) ~ [data-testid="stHorizontalBlock"] > div:first-child [data-testid="stButton"] button {{
            display: inline-flex !important; align-items: center !important; gap: 9px !important;
            background: rgba(255,255,255,.1) !important;
            backdrop-filter: blur(20px) !important;
            -webkit-backdrop-filter: blur(20px) !important;
            border: 1px solid rgba(255,255,255,.22) !important;
            border-radius: 100px !important; padding: 8px 18px 8px 8px !important;
            color: white !important; font-weight: 800 !important; font-size: 13.5px !important;
            letter-spacing: -.1px !important; box-shadow: none !important;
        }}
        div:has(#top-nav-sentinel) ~ [data-testid="stHorizontalBlock"] > div:first-child [data-testid="stButton"] button::before {{
            content: "신";
            display: inline-flex; align-items: center; justify-content: center;
            width: 28px; height: 28px; min-width: 28px;
            background: white; border-radius: 50%;
            font-size: 12px; font-weight: 900; color: #003082; flex-shrink: 0;
        }}
        div:has(#top-nav-sentinel) ~ [data-testid="stHorizontalBlock"] > div:first-child [data-testid="stButton"] button:hover {{
            background: rgba(255,255,255,.18) !important; transform: none !important;
        }}
        /* ── Icon nav buttons (word/allow/save/prod) ── */
        div:has(#top-nav-sentinel) button[data-testid="stBaseButton-secondary"] {{
            background: rgba(255,255,255,.1) !important;
            backdrop-filter: blur(12px) !important;
            -webkit-backdrop-filter: blur(12px) !important;
            border: 1px solid rgba(255,255,255,.22) !important;
            color: white !important;
            box-shadow: none !important;
        }}
        div:has(#top-nav-sentinel) button[data-testid="stBaseButton-secondary"]:hover {{
            background: rgba(255,255,255,.18) !important;
            transform: none !important;
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
            a.src = '/app/static/bgm1.mp3';
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
    {"label": "13살 이상", "value": "all",    "emoji": "🧑", "desc": "예산·이자·금융 선택"},
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
        header[data-testid="stHeader"], footer { display:none !important; }
        #MainMenu { visibility:hidden !important; }
        section[data-testid="stSidebar"] { display:none !important; }

        /* ── Background ── */
        .stApp, section[data-testid="stMain"], section[data-testid="stMain"] > div, .main > div {
            background: linear-gradient(150deg, #00112e 0%, #001a5c 30%, #003082 65%, #0057c2 100%) !important;
        }
        .block-container { background:transparent !important; max-width:900px !important; padding-top:0 !important; }

        /* ── Ambient orbs ── */
        .stApp::before {
            content:''; position:fixed; top:-200px; right:-100px;
            width:500px; height:500px; border-radius:50%;
            background:radial-gradient(circle,rgba(99,102,241,.18) 0%,transparent 70%);
            pointer-events:none; z-index:0;
        }
        .stApp::after {
            content:''; position:fixed; bottom:-150px; left:-80px;
            width:400px; height:400px; border-radius:50%;
            background:radial-gradient(circle,rgba(0,87,194,.22) 0%,transparent 70%);
            pointer-events:none; z-index:0;
        }

        /* ── Animations ── */
        @keyframes floatY    { 0%,100%{transform:translateY(0)} 50%{transform:translateY(-14px)} }
        @keyframes fadeUp    { from{opacity:0;transform:translateY(30px)} to{opacity:1;transform:translateY(0)} }
        @keyframes fadeIn    { from{opacity:0} to{opacity:1} }
        @keyframes bounce    { 0%,100%{transform:translateY(0)} 40%{transform:translateY(-18px)} 60%{transform:translateY(-7px)} }
        @keyframes popIn     { from{opacity:0;transform:scale(.82)} to{opacity:1;transform:scale(1)} }
        @keyframes glow      { 0%,100%{filter:drop-shadow(0 0 8px rgba(255,255,255,.3))} 50%{filter:drop-shadow(0 0 22px rgba(255,255,255,.7))} }
        @keyframes dotPulse  { 0%,100%{transform:scale(1)} 50%{transform:scale(1.4)} }

        /* ── Glass card ── */
        .fq-card {
            background: rgba(255,255,255,.06);
            backdrop-filter: blur(28px);
            -webkit-backdrop-filter: blur(28px);
            border: 1px solid rgba(255,255,255,.14);
            border-radius: 28px;
            padding: 36px 16px 28px;
            text-align: center;
            transition: all .3s cubic-bezier(.34,1.56,.64,1);
            margin-bottom: 8px;
            position: relative;
            overflow: hidden;
            box-shadow: 0 8px 32px rgba(0,0,0,.22), inset 0 1px 0 rgba(255,255,255,.08);
        }
        .fq-card::before {
            content: '';
            position: absolute; top: 0; left: 0; right: 0; height: 1px;
            background: linear-gradient(90deg, transparent 0%, rgba(255,255,255,.28) 50%, transparent 100%);
        }
        .fq-card:hover {
            background: rgba(255,255,255,.12);
            border-color: rgba(255,255,255,.32);
            transform: translateY(-12px) scale(1.03);
            box-shadow: 0 32px 64px rgba(0,0,0,.38), inset 0 1px 0 rgba(255,255,255,.15);
        }

        /* ── Speech bubble ── */
        .fq-bubble {
            background: rgba(255,255,255,.07);
            backdrop-filter: blur(20px);
            -webkit-backdrop-filter: blur(20px);
            border: 1px solid rgba(255,255,255,.16);
            border-radius: 24px;
            padding: 24px 28px;
            margin: 18px auto 22px;
            max-width: 600px;
            text-align: left;
            animation: fadeUp .55s cubic-bezier(.34,1.56,.64,1);
            box-shadow: 0 12px 40px rgba(0,0,0,.22), inset 0 1px 0 rgba(255,255,255,.08);
            position: relative;
        }
        .fq-bubble::before {
            content: '';
            position: absolute; top: 0; left: 0; right: 0; height: 1px;
            background: linear-gradient(90deg, transparent, rgba(255,255,255,.24), transparent);
            border-radius: 24px 24px 0 0;
        }

        /* ── Progress dots ── */
        .fq-dots { text-align:center; margin:10px 0 0; display:flex; align-items:center; justify-content:center; gap:8px; }
        .fq-dot  {
            display:inline-block; width:8px; height:8px; border-radius:50%;
            background:rgba(255,255,255,.22); transition:all .3s cubic-bezier(.34,1.56,.64,1);
        }
        .fq-dot.active {
            background:white; width:24px; border-radius:100px;
            box-shadow: 0 0 12px rgba(255,255,255,.6);
            animation: dotPulse 2s ease-in-out infinite;
        }

        /* ── Buttons (glass pill) ── */
        .stButton > button {
            border-radius: 100px !important;
            font-weight: 700 !important;
            font-size: .93rem !important;
            letter-spacing: .1px !important;
            transition: all .22s cubic-bezier(.34,1.56,.64,1) !important;
            color: rgba(255,255,255,.92) !important;
            background: rgba(255,255,255,.1) !important;
            backdrop-filter: blur(12px) !important;
            -webkit-backdrop-filter: blur(12px) !important;
            border: 1px solid rgba(255,255,255,.22) !important;
            padding: 11px 26px !important;
            box-shadow: 0 2px 14px rgba(0,0,0,.22),
                        inset 0 1px 0 rgba(255,255,255,.15) !important;
        }
        .stButton > button:hover {
            background: rgba(255,255,255,.18) !important;
            border-color: rgba(255,255,255,.38) !important;
            color: white !important;
            transform: translateY(-2px) scale(1.02) !important;
            box-shadow: 0 8px 28px rgba(0,0,0,.3),
                        inset 0 1px 0 rgba(255,255,255,.22) !important;
        }
        .stButton > button[kind="primary"] {
            background: linear-gradient(135deg, #4361ee 0%, #0057c2 100%) !important;
            color: white !important;
            border: none !important;
            box-shadow: 0 4px 20px rgba(67,97,238,.55) !important;
        }
        .stButton > button[kind="primary"]:hover {
            background: linear-gradient(135deg, #3651d4 0%, #0047a8 100%) !important;
            box-shadow: 0 8px 32px rgba(67,97,238,.72) !important;
            transform: translateY(-3px) scale(1.02) !important;
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
            box-shadow: none !important; border-radius: 28px !important;
            transform: none !important;
        }
        div:has(#char-select-sentinel) ~ [data-testid="stHorizontalBlock"] [data-testid="stButton"] button:hover,
        div:has(#age-select-sentinel)  ~ [data-testid="stHorizontalBlock"] [data-testid="stButton"] button:hover {
            transform: none !important; box-shadow: none !important; background: transparent !important;
        }
        div:has(#char-select-sentinel) ~ [data-testid="stHorizontalBlock"] [data-testid="stColumn"]:has([data-testid="stButton"] button:hover) .fq-card,
        div:has(#age-select-sentinel)  ~ [data-testid="stHorizontalBlock"] [data-testid="stColumn"]:has([data-testid="stButton"] button:hover) .fq-card {
            background: rgba(255,255,255,.14) !important;
            border-color: rgba(255,255,255,.38) !important;
            transform: translateY(-12px) scale(1.03) !important;
            box-shadow: 0 32px 64px rgba(0,0,0,.4) !important;
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
        /* ── 버튼 글씨 강제 지정 ── */
        [data-testid="stButton"] p,
        [data-testid="stButton"] span,
        [data-testid="stButton"] [data-testid="stMarkdownContainer"] p,
        [data-testid="stButton"] [data-testid="stMarkdownContainer"] span { color: rgba(255,255,255,.92) !important; }
        [data-testid="stButton"] button[kind="primary"] p,
        [data-testid="stButton"] button[kind="primary"] span,
        [data-testid="stButton"] button[kind="primary"] [data-testid="stMarkdownContainer"] p,
        [data-testid="stButton"] button[kind="primary"] [data-testid="stMarkdownContainer"] span { color: white !important; }
        div[data-testid="stSpinner"] p, div[data-testid="stSpinner"] span { color: white !important; }
        hr { border-color: rgba(255,255,255,.1) !important; margin: 1.2rem 0 !important; }

        /* ── Shinhan logo button (onboarding) ── */
        div:has(#top-nav-sentinel) ~ [data-testid="stHorizontalBlock"] > div:first-child [data-testid="stButton"] {
            margin-top: 0 !important; z-index: auto !important;
        }
        div:has(#top-nav-sentinel) ~ [data-testid="stHorizontalBlock"] > div:first-child [data-testid="stButton"] button {
            display: inline-flex !important; align-items: center !important; gap: 9px !important;
            background: rgba(255,255,255,.1) !important;
            backdrop-filter: blur(20px) !important; -webkit-backdrop-filter: blur(20px) !important;
            border: 1px solid rgba(255,255,255,.22) !important;
            border-radius: 100px !important; padding: 8px 18px 8px 8px !important;
            color: white !important; font-weight: 800 !important; font-size: 13.5px !important;
            box-shadow: none !important;
        }
        div:has(#top-nav-sentinel) ~ [data-testid="stHorizontalBlock"] > div:first-child [data-testid="stButton"] button::before {
            content: "신";
            display: inline-flex; align-items: center; justify-content: center;
            width: 28px; height: 28px; min-width: 28px;
            background: white; border-radius: 50%;
            font-size: 12px; font-weight: 900; color: #003082; flex-shrink: 0;
        }
        div:has(#top-nav-sentinel) ~ [data-testid="stHorizontalBlock"] > div:first-child [data-testid="stButton"] button:hover {
            background: rgba(255,255,255,.18) !important; transform: none !important;
        }
        /* ── All other nav buttons ── */
        div:has(#top-nav-sentinel) button[data-testid="stBaseButton-secondary"] {
            background: rgba(255,255,255,.1) !important;
            backdrop-filter: blur(12px) !important;
            -webkit-backdrop-filter: blur(12px) !important;
            border: 1px solid rgba(255,255,255,.22) !important;
            color: white !important;
            box-shadow: none !important;
        }
        div:has(#top-nav-sentinel) button[data-testid="stBaseButton-secondary"]:hover {
            background: rgba(255,255,255,.18) !important;
            transform: none !important;
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
        if st.button("신한은행", key=f"logo_home_{step}", use_container_width=False):
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
        if st.button("신한은행", key="top_nav_home", use_container_width=False):
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
        <div style="text-align:center;padding:40px 0 12px;animation:fadeUp .7s cubic-bezier(.34,1.56,.64,1);">
          <div style="display:inline-block;background:rgba(255,255,255,.08);backdrop-filter:blur(20px);
                      border:1px solid rgba(255,255,255,.18);border-radius:100px;
                      padding:6px 18px;font-size:.78rem;color:rgba(255,255,255,.7);
                      letter-spacing:1.5px;font-weight:700;margin-bottom:20px;">
            ✦ 신한은행 금융교육 게임 ✦
          </div>
          <div style="font-size:4.2rem;animation:bounce 1.3s ease-out;display:block;margin-bottom:8px;">🚀</div>
          <h1 style="font-size:3.2rem;font-weight:900;letter-spacing:-2px;margin:0 0 10px;
                     background:linear-gradient(135deg,#fff 0%,#a5c8ff 100%);
                     -webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;
                     line-height:1.1;">쏠어드벤쳐</h1>
          <p style="color:rgba(255,255,255,.72);font-size:1.08rem;margin:0;line-height:1.7;">
            금융 지식으로 악당을 물리치는 어린이 모험! 🌟
          </p>
        </div>
        <div style="text-align:center;margin:28px 0 16px;">
          <span style="display:inline-block;background:linear-gradient(135deg,rgba(255,215,0,.2),rgba(255,215,0,.08));
                       border:1px solid rgba(255,215,0,.35);border-radius:100px;
                       padding:8px 20px;color:#ffd700;font-size:.92rem;font-weight:800;">
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
            f' style="cursor:pointer;background:linear-gradient(160deg,rgba(255,255,255,.09),'
            f'rgba(255,255,255,.03));border:2px solid {ch["color"]}55;border-radius:20px;'
            f'padding:28px 14px;text-align:center;flex:1;transition:transform .22s,box-shadow .22s;"'
            f' onmouseover="this.style.transform=\'translateY(-6px)\';this.style.boxShadow=\'0 14px 40px rgba(0,0,0,.45)\'"'
            f' onmouseout="this.style.transform=\'\';this.style.boxShadow=\'\'">'
            + _char_icon_html(ch)
            + f'<h3 style="color:{ch["color"]};margin:0 0 6px;font-size:1.1rem;font-weight:900;letter-spacing:-.2px;">{ch["name"]}</h3>'
            + f'<div style="width:32px;height:3px;background:{ch["color"]};border-radius:100px;margin:0 auto 10px;opacity:.7;"></div>'
            + f'<p style="color:rgba(255,255,255,.65);font-size:.8rem;margin:0;line-height:1.6;">{ch["desc"]}</p>'
            + '</div>'
        )

    components.html(
        f"""<!DOCTYPE html>
<html><head>
<style>
  body {{ margin:0; background:transparent; font-family:'Segoe UI',sans-serif; }}
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
        icon = age_icons[i] or f'<div style="font-size:3.4rem;margin-bottom:10px;">{ag["emoji"]}</div>'
        age_cards_html += (
            f'<div class="fq-card" onclick="selectAge(\'{ag["label"]}\')"'
            f' style="cursor:pointer;background:linear-gradient(160deg,rgba(255,255,255,.09),'
            f'rgba(255,255,255,.03));border:2px solid rgba(255,215,0,.35);border-radius:20px;'
            f'padding:28px 14px;text-align:center;flex:1;transition:transform .22s,box-shadow .22s;"'
            f' onmouseover="this.style.transform=\'translateY(-6px)\';this.style.boxShadow=\'0 14px 40px rgba(0,0,0,.45)\'"'
            f' onmouseout="this.style.transform=\'\';this.style.boxShadow=\'\'">'
            + icon
            + f'<h3 style="color:#ffd700;margin:0 0 6px;font-size:1.1rem;font-weight:900;letter-spacing:-.2px;">{ag["label"]}</h3>'
            + f'<div style="width:32px;height:3px;background:#ffd700;border-radius:100px;margin:0 auto 10px;opacity:.6;"></div>'
            + f'<p style="color:rgba(255,255,255,.65);font-size:.8rem;margin:0;line-height:1.6;">{ag["desc"]}</p>'
            + '</div>'
        )

    components.html(
        f"""<!DOCTYPE html>
<html><head>
<style>
  body {{ margin:0; background:transparent; font-family:'Segoe UI',sans-serif; }}
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
            f'<div style="margin:6px 0 4px"><span style="background:{c}33;color:{c};'
            f'font-size:.68rem;padding:3px 10px;border-radius:100px;font-weight:800;'
            f'letter-spacing:.3px;">📈 주식·투자</span></div>'
            if w["id"] == "space"
            else '<div style="height:6px"></div>'
        )
        label = f'{w["emoji"]} {w["name"]}'
        world_cards_html += (
            f'<div class="fq-card" onclick="selectWorld(\'{label}\')"'
            f' style="cursor:pointer;background:linear-gradient(160deg,rgba(255,255,255,.09),'
            f'rgba(255,255,255,.03));border:2px solid {c}44;border-radius:20px;'
            f'padding:22px 14px;text-align:center;display:flex;flex-direction:column;'
            f'align-items:center;transition:transform .22s,box-shadow .22s;"'
            f' onmouseover="this.style.transform=\'translateY(-6px)\';this.style.boxShadow=\'0 14px 40px rgba(0,0,0,.45)\'"'
            f' onmouseout="this.style.transform=\'\';this.style.boxShadow=\'\'">'
            + f'<div style="font-size:3.2rem;margin-bottom:6px;">{w["emoji"]}</div>'
            + badge
            + f'<h3 style="color:{c};margin:0 0 6px;font-size:1.05rem;font-weight:900;letter-spacing:-.2px;">{w["name"]}</h3>'
            + f'<div style="background:rgba(239,68,68,.15);border:1px solid rgba(239,68,68,.3);'
            f'border-radius:100px;padding:3px 10px;font-size:.72rem;color:#fca5a5;font-weight:700;margin-bottom:8px;">'
            f'👿 {w["villain"]}</div>'
            + f'<p style="color:rgba(255,255,255,.62);font-size:.79rem;margin:0;line-height:1.65;flex:1;">{w["desc"]}</p>'
            + '</div>'
        )

    components.html(
        f"""<!DOCTYPE html>
<html><head>
<style>
  body {{ margin:0; background:transparent; font-family:'Segoe UI',sans-serif; }}
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
        st.rerun()

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
        st.balloons()
        st.success(f"🏆 {world_ko} 클리어! 보스를 물리쳤어요!")
        st.rerun()

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

    # Deduplicate: after st.rerun() the component returns the same last value;
    # use the ts timestamp to skip events that were already processed.
    if result:
        ev_ts = result.get("ts")
        if ev_ts and ev_ts == st.session_state.get("_last_ev_ts"):
            result = None
        elif ev_ts:
            st.session_state["_last_ev_ts"] = ev_ts

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
        .block-container { max-width: 760px !important; }
        .news-card {
            background: rgba(255,255,255,.06);
            backdrop-filter: blur(24px);
            -webkit-backdrop-filter: blur(24px);
            border: 1px solid rgba(255,255,255,.12);
            border-radius: 24px;
            padding: 24px 26px;
            margin-bottom: 16px;
            box-shadow: 0 8px 32px rgba(0,0,0,.2), inset 0 1px 0 rgba(255,255,255,.07);
            transition: all .25s ease;
            position: relative; overflow: hidden;
        }
        .news-card::before {
            content: '';
            position: absolute; top: 0; left: 0; right: 0; height: 1px;
            background: linear-gradient(90deg, transparent, rgba(255,255,255,.2), transparent);
        }
        .news-header { display: flex; align-items: flex-start; gap: 16px; margin-bottom: 14px; }
        .news-emoji-box {
            width: 52px; height: 52px; min-width: 52px; border-radius: 16px;
            background: rgba(255,255,255,.1); display: flex; align-items: center;
            justify-content: center; font-size: 1.8rem;
        }
        .news-title { font-size: 1.05rem; font-weight: 800; color: white; line-height: 1.4; margin: 0; }
        .news-summary { font-size: .93rem; color: rgba(255,255,255,.72); line-height: 1.85; margin-bottom: 14px; }
        .news-lesson {
            display: inline-flex; align-items: center; gap: 8px;
            background: rgba(255,215,0,.12); border: 1px solid rgba(255,215,0,.28);
            border-radius: 12px; padding: 8px 14px; margin-bottom: 12px;
            font-size: .87rem; color: #fde68a; font-weight: 700; line-height: 1.5;
        }
        .news-link a {
            font-size: .82rem; color: rgba(165,180,252,.8); text-decoration: none;
            font-weight: 600; display: inline-flex; align-items: center; gap: 4px;
        }
        .news-link a:hover { color: white; }
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        '<div style="padding:8px 0 4px;">'
        '<h2 style="color:white;font-size:1.7rem;font-weight:900;letter-spacing:-.6px;margin:0 0 6px;">📰 오늘의 주식 뉴스</h2>'
        '<p style="color:rgba(255,255,255,.6);font-size:.93rem;margin:0;">쏠쏠이가 어린이도 이해하기 쉽게 설명해줄게요! 🌟</p>'
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

    if news_items:
        for item in news_items:
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

        .rv-bento {{ display:grid; grid-template-columns:1fr 1fr 1fr; gap:12px; margin:24px 0 20px; }}
        .rv-box {{
            background:{tbg};
            backdrop-filter:blur(20px); -webkit-backdrop-filter:blur(20px);
            border:1px solid {tc}33; border-radius:22px;
            padding:24px 12px; text-align:center;
            box-shadow:0 4px 20px rgba(0,0,0,.18), inset 0 1px 0 rgba(255,255,255,.06);
            transition: all .25s ease;
        }}
        .rv-box:hover {{ transform:translateY(-4px); box-shadow:0 12px 32px rgba(0,0,0,.28); }}
        .rv-num {{ font-size:2.1rem; font-weight:900; color:{tc}; line-height:1.2; }}
        .rv-lbl {{ font-size:.75rem; color:rgba(255,255,255,.5); margin-top:6px; letter-spacing:.3px; }}

        .rv-tips-hd {{ color:white; font-size:1rem; font-weight:800; margin:6px 0 14px; letter-spacing:-.3px; }}
        .rv-tip {{
            display:flex; align-items:flex-start; gap:12px;
            background:rgba(255,255,255,.05);
            backdrop-filter:blur(12px);
            border:1px solid rgba(255,255,255,.1);
            border-left:3px solid {tc};
            border-radius:0 16px 16px 0;
            padding:13px 16px; margin-bottom:10px;
            color:rgba(255,255,255,.8); font-size:.9rem; line-height:1.7;
        }}
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
        <div style="background:linear-gradient(135deg,rgba(255,105,180,.12),rgba(255,20,147,.06));
                    border:1px solid rgba(255,105,180,.3);border-radius:22px;
                    padding:20px 22px;margin:20px 0 8px;text-align:center;">
          <div style="font-size:2rem;margin-bottom:6px;">📱</div>
          <p style="color:white;font-weight:800;font-size:1rem;margin:0 0 4px;">엄마에게 조르기</p>
          <p style="color:rgba(255,255,255,.55);font-size:.82rem;margin:0;">퀴즈 결과를 엄마 핸드폰으로 보내봐요!</p>
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


def _build_msg_text(gs: GameState) -> str:
    name  = gs.character_name or "아이"
    coins = gs.coins
    done  = len(gs.completed_missions)
    wko   = {"space": "별빛 금융 은하", "dinosaur": "공룡 정글",
              "magic": "마법왕국", "ocean": "파도 저금섬"}.get(gs.world or "space", "핀퀘스트")
    tier  = "주식 마스터" if coins >= 100 else ("금융 전사" if coins >= 50 else "새싹 탐험가")
    if done > 0:
        return (
            f"[신한 쏠어드벤쳐] {name}이(가) {wko}를 탐험했어요! 🎉\n"
            f"퀴즈 {done}개 완료, 쏠코인 {coins}개 획득!\n"
            f"등급: {tier} 🏆\n열심히 금융공부 했으니 용돈 올려주세요~ 🙏"
        )
    return (
        f"[신한 쏠어드벤쳐] {name}이(가) 열심히 금융 공부 중이에요! 📚\n"
        f"핀퀘스트에서 저축·투자·주식을 배우고 있어요!\n"
        f"용돈 올려주시면 더 열심히 할게요~ 🙏"
    )


def _render_kakao_btn(msg_text: str, height: int = 62):
    """st.components.v1.html()로 카카오 공유 버튼 렌더 (JS 실행 보장)."""
    import streamlit.components.v1 as components
    kakao_key = os.environ.get("KAKAO_JS_KEY", "")
    msg_js    = json.dumps(msg_text)

    if not kakao_key:
        st.markdown(
            """
            <div style="background:rgba(254,229,0,.08);border:1px solid rgba(254,229,0,.25);
                        border-radius:18px;padding:14px 20px;text-align:center;">
              <p style="color:#fde68a;font-size:.85rem;margin:0;">
                💛 <b>.env</b>에 <code>KAKAO_JS_KEY</code>를 추가하면 카카오톡 버튼이 활성화돼요!
              </p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    html = f"""
    <!DOCTYPE html>
    <html>
    <head><meta charset="utf-8"></head>
    <body style="margin:0;padding:4px 0;background:transparent;">
      <button onclick="doShare()" id="kakaoBtn" style="
          display:flex;align-items:center;justify-content:center;gap:10px;
          width:100%;padding:14px 0;border:none;cursor:pointer;
          background:#FEE500;color:#ffffff;font-weight:800;font-size:1rem;
          border-radius:12px;box-shadow:0 4px 16px rgba(254,229,0,.4);">
        <svg width="22" height="22" viewBox="0 0 38 38" fill="none">
          <ellipse cx="19" cy="18" rx="18" ry="16" fill="#191600"/>
          <path d="M19 6C12.4 6 7 10.5 7 16c0 3.5 2.1 6.6 5.4 8.5l-1.4 5.1 5.9-3.9c.97.15 1.97.23 3.1.23 6.6 0 12-4.5 12-10S25.6 6 19 6z" fill="#FEE500"/>
        </svg>
        💛 카카오톡으로 보내기
      </button>
      <div id="errMsg" style="margin-top:8px;font-size:.8rem;color:#f87171;display:none;"></div>
      <script src="https://t1.kakaocdn.net/kakao_js_sdk/2.7.2/kakao.min.js"
              integrity="sha384-TiCUE00h649CAMonG018J2ujOgDKW/kVWlChEuu4jK2vxfAAD0eZxzCKakxg55G4"
              crossorigin="anonymous"></script>
      <script>
        var MSG = {msg_js};
        window.onload = function() {{
          try {{
            if (typeof Kakao !== 'undefined' && !Kakao.isInitialized())
              Kakao.init('{kakao_key}');
          }} catch(e) {{}}
        }};
        function showErr(msg) {{
          var el = document.getElementById('errMsg');
          el.textContent = msg; el.style.display = 'block';
        }}
        function shareViaWebAPI() {{
          if (navigator.share) {{
            navigator.share({{ title: '쏠어드벤쳐', text: MSG }})
              .catch(function(){{}});
          }} else {{
            navigator.clipboard.writeText(MSG).then(function() {{
              alert('메시지가 복사됐어요!\\n카카오톡을 열어서 붙여넣기 해주세요 💛');
            }}).catch(function() {{
              alert(MSG);
            }});
          }}
        }}
        function doShare() {{
          var siteUrl = window.location.origin;
          if (typeof Kakao === 'undefined') {{
            showErr('카카오 SDK를 불러오지 못했어요. 인터넷 연결을 확인해주세요.');
            shareViaWebAPI(); return;
          }}
          try {{
            if (!Kakao.isInitialized()) Kakao.init('{kakao_key}');
            Kakao.Share.sendDefault({{
              objectType: 'text',
              text: MSG,
              link: {{
                mobileWebUrl: siteUrl,
                webUrl: siteUrl,
              }}
            }});
          }} catch(e) {{
            showErr('카카오 에러: ' + e.message);
            shareViaWebAPI();
          }}
        }}
      </script>
    </body>
    </html>
    """
    components.html(html, height=height + 10)


def _send_result_sms(gs: GameState):
    """결과 페이지용 카카오 공유 버튼 렌더."""
    msg_text = _build_msg_text(gs)
    st.markdown(
        f"""
        <div style="background:rgba(255,255,255,.07);backdrop-filter:blur(20px);
                    border:1px solid rgba(255,105,180,.3);border-radius:22px;
                    padding:20px 22px;margin:8px 0;">
          <p style="color:rgba(255,255,255,.5);font-size:.75rem;font-weight:700;
                    letter-spacing:.5px;margin:0 0 10px;">📨 보낼 메시지 미리보기</p>
          <p style="color:white;font-size:.92rem;line-height:1.8;white-space:pre-line;margin:0;">{msg_text}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    _render_kakao_btn(msg_text)


# ── 엄마 조르기 페이지 ────────────────────────────────────────────────────────

def page_joreogi(gs: GameState):
    inject_css(gs.world or "space")
    _render_top_nav(gs)

    msg_text = _build_msg_text(gs)
    coins    = gs.coins
    done     = len(gs.completed_missions)

    st.markdown(
        """
        <div style="text-align:center;padding:32px 0 16px;animation:fadeUp .6s ease;">
          <div style="font-size:4rem;">💛</div>
          <h1 style="color:white;font-size:1.8rem;font-weight:900;margin:12px 0 6px;">엄마에게 조르기</h1>
          <p style="color:rgba(255,255,255,.6);font-size:.95rem;">카카오톡으로 보내고 용돈을 올려달라고 해봐요!</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── 메시지 미리보기 ───────────────────────────────────────────────
    st.markdown(
        f"""
        <div style="background:rgba(255,255,255,.07);backdrop-filter:blur(20px);
                    border:1px solid rgba(255,105,180,.3);border-radius:22px;
                    padding:24px;margin:0 0 16px;">
          <p style="color:rgba(255,255,255,.5);font-size:.75rem;font-weight:700;
                    letter-spacing:.5px;margin:0 0 12px;">📨 보낼 메시지 미리보기</p>
          <p style="color:white;font-size:.95rem;line-height:1.85;white-space:pre-line;margin:0;">{msg_text}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── 카카오 공유 버튼 ─────────────────────────────────────────────
    _render_kakao_btn(msg_text)

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
            display:inline-block; background:rgba(255,215,0,.15);
            border:1px solid rgba(255,215,0,.3); border-radius:100px;
            padding:5px 16px; color:#fde68a; font-size:.78rem; font-weight:800;
            letter-spacing:1px; margin-bottom:16px;
        }}
        .wd-card {{
            background:rgba(255,255,255,.07);
            backdrop-filter:blur(28px); -webkit-backdrop-filter:blur(28px);
            border:1px solid rgba(255,255,255,.14); border-radius:28px;
            padding:36px 32px; margin:16px 0;
            box-shadow:0 12px 40px rgba(0,0,0,.25), inset 0 1px 0 rgba(255,255,255,.08);
            position:relative; overflow:hidden;
        }}
        .wd-card::before {{
            content:''; position:absolute; top:0; left:0; right:0; height:1px;
            background:linear-gradient(90deg,transparent,rgba(255,255,255,.25),transparent);
        }}
        .wd-tip {{
            background:rgba(255,215,0,.1); border:1px solid rgba(255,215,0,.25);
            border-radius:16px; padding:14px 18px; margin-top:20px;
            color:#fde68a; font-size:.9rem; line-height:1.7; font-weight:600;
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
        <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px;margin:18px 0 24px;">
          <div style="background:rgba(74,222,128,.1);border:1px solid rgba(74,222,128,.3);border-radius:20px;padding:20px 12px;text-align:center;">
            <div style="font-size:1.6rem;font-weight:900;color:#4ade80;">+{total_in:,}</div>
            <div style="font-size:.75rem;color:rgba(255,255,255,.5);margin-top:4px;">받은 용돈</div>
          </div>
          <div style="background:rgba(248,113,113,.1);border:1px solid rgba(248,113,113,.3);border-radius:20px;padding:20px 12px;text-align:center;">
            <div style="font-size:1.6rem;font-weight:900;color:#f87171;">-{total_out:,}</div>
            <div style="font-size:.75rem;color:rgba(255,255,255,.5);margin-top:4px;">쓴 돈</div>
          </div>
          <div style="background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.15);border-radius:20px;padding:20px 12px;text-align:center;">
            <div style="font-size:1.6rem;font-weight:900;color:{balance_color};">{balance:,}원</div>
            <div style="font-size:.75rem;color:rgba(255,255,255,.5);margin-top:4px;">남은 용돈</div>
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
                f'background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.1);'
                f'border-radius:14px;padding:12px 16px;margin-bottom:8px;">'
                f'<span style="color:rgba(255,255,255,.8);font-size:.9rem;">{r["emoji"]} {r["desc"]}</span>'
                f'<span style="color:{col};font-weight:800;font-size:.95rem;">{sign}{r["amount"]:,}원</span>'
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
        bar_color = "#4ade80" if pct >= 100 else "#818cf8"
        st.markdown(
            f"""
            <div style="background:rgba(255,255,255,.07);backdrop-filter:blur(24px);
                        border:1px solid rgba(255,255,255,.13);border-radius:28px;padding:28px;margin:16px 0;">
              <div style="text-align:center;margin-bottom:20px;">
                <div style="font-size:4rem;animation:floatY 2.8s ease-in-out infinite;">{pig_emoji}</div>
                <div style="color:white;font-size:1.25rem;font-weight:900;margin:10px 0 4px;">{goal_name or "저축 목표"}</div>
                <div style="color:rgba(255,255,255,.55);font-size:.85rem;">{saved:,}원 / {goal:,}원</div>
              </div>
              <div style="background:rgba(255,255,255,.1);border-radius:100px;height:18px;overflow:hidden;margin-bottom:8px;">
                <div style="background:linear-gradient(90deg,{bar_color},{bar_color}aa);height:100%;
                             width:{pct}%;border-radius:100px;transition:width .5s ease;
                             box-shadow:0 0 12px {bar_color}88;"></div>
              </div>
              <div style="text-align:right;color:{bar_color};font-size:.88rem;font-weight:800;">{pct}% 달성!</div>
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
        .pd-hero { text-align:center; padding:24px 0 16px; animation:fadeUp .7s ease-out; }
        .pd-card {
            background:rgba(255,255,255,.06);
            backdrop-filter:blur(28px); -webkit-backdrop-filter:blur(28px);
            border:1px solid rgba(255,255,255,.12); border-radius:28px;
            padding:28px 26px; margin-bottom:18px;
            box-shadow:0 8px 32px rgba(0,0,0,.2), inset 0 1px 0 rgba(255,255,255,.08);
            position:relative; overflow:hidden;
        }
        .pd-card::before {
            content:''; position:absolute; top:0; left:0; right:0; height:1px;
            background:linear-gradient(90deg,transparent,rgba(255,255,255,.22),transparent);
        }
        .pd-tag {
            display:inline-block; border-radius:100px;
            padding:3px 12px; font-size:.72rem; font-weight:800; letter-spacing:.3px;
            margin-bottom:10px;
        }
        .pd-diff { display:flex; gap:4px; margin-bottom:8px; }
        .pd-dot-on  { width:10px; height:10px; border-radius:50%; background:rgba(255,255,255,.9); }
        .pd-dot-off { width:10px; height:10px; border-radius:50%; background:rgba(255,255,255,.2); }
        .pd-point {
            display:flex; align-items:flex-start; gap:8px;
            color:rgba(255,255,255,.75); font-size:.88rem; line-height:1.6;
            margin-bottom:6px;
        }
        .pd-analogy {
            background:rgba(255,215,0,.1); border:1px solid rgba(255,215,0,.25);
            border-radius:14px; padding:12px 16px; margin-top:16px;
            color:#fde68a; font-size:.87rem; line-height:1.7; font-weight:600;
        }
        .pd-tip {
            background:rgba(255,255,255,.05); border-left:3px solid rgba(255,255,255,.3);
            border-radius:0 12px 12px 0; padding:11px 14px; margin:6px 0;
            color:rgba(255,255,255,.72); font-size:.85rem; line-height:1.65;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        """
        <div class="pd-hero">
          <div style="display:inline-block;background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.18);
                      border-radius:100px;padding:5px 16px;color:rgba(255,255,255,.6);font-size:.76rem;
                      font-weight:700;letter-spacing:1.2px;margin-bottom:16px;">
            ✦ 신한은행 추천 상품 ✦
          </div>
          <div style="font-size:3rem;animation:bounce 1.2s ease-out;display:block;margin-bottom:8px;">🏦</div>
          <h2 style="color:white;font-size:1.8rem;font-weight:900;letter-spacing:-.6px;margin:0 0 8px;">
            어린이 금융 상품 추천
          </h2>
          <p style="color:rgba(255,255,255,.6);font-size:.95rem;margin:0;">
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

        st.markdown(
            f'<div class="pd-card">'
            f'<div style="display:flex;align-items:flex-start;justify-content:space-between;margin-bottom:12px;">'
            f'  <div>'
            f'    <span class="pd-tag" style="background:{p["tag_color"]}22;color:{p["tag_color"]};border:1px solid {p["tag_color"]}44;">{p["tag"]}</span>'
            f'    <div class="pd-diff">{diff_dots}'
            f'      <span style="color:rgba(255,255,255,.4);font-size:.72rem;margin-left:4px;">난이도: {p["difficulty_label"]}</span>'
            f'    </div>'
            f'  </div>'
            f'  <div style="font-size:2.8rem;">{p["emoji"]}</div>'
            f'</div>'
            f'<h3 style="color:white;font-size:1.12rem;font-weight:900;margin:0 0 4px;letter-spacing:-.3px;">{p["name"]}</h3>'
            f'<p style="color:{p["tag_color"]};font-size:.85rem;font-weight:700;margin:0 0 12px;">👶 대상: {p["target"]}</p>'
            f'<p style="color:rgba(255,255,255,.5);font-size:.75rem;font-weight:800;letter-spacing:.5px;margin:0 0 6px;">한 마디로?</p>'
            f'<p style="color:white;font-size:1rem;font-weight:700;margin:0 0 14px;">{p["headline"]}</p>'
            f'<p style="color:rgba(255,255,255,.7);font-size:.9rem;line-height:1.8;margin:0 0 14px;">{p["simple"]}</p>'
            f'<div>{points_html}</div>'
            f'<div class="pd-analogy">🌟 {p["analogy"]}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
        if st.button(f"🔗 {p['name']} 자세히 보기", key=f"pd_{p['id']}", use_container_width=True):
            st.markdown(
                f'<script>window.open("{p["link"]}", "_blank")</script>',
                unsafe_allow_html=True,
            )

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
    worlds = load_worlds()
    missions = load_missions()
    gs = GameState()
    badge_engine = BadgeEngine()

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
