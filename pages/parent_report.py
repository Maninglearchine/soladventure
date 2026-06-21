"""
Parent Report Page — 3-tab breakdown of today's financial learning.
"""
from __future__ import annotations

import json
import os

import plotly.graph_objects as go
import streamlit as st
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_core.runnables import RunnablePassthrough

from ui.portfolio_chart import PortfolioChart, WORLD_COLORS

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ── RAG 설정 ─────────────────────────────────────────────────────────────────

_RAG_PDF_PATH = os.path.join(BASE, "rag", "증여법관련.pdf")

_RAG_PROMPT = """
당신은 대한민국 자산 증여 전문 상담사입니다.
아래 참고 문서를 바탕으로 질문에 답변하세요.

답변 작성 규칙:
1. 구체적인 금액·세율·기간·한도를 숫자로 명시하세요 (예: 10년간 2,000만 원, 세율 10~50%).
2. 핵심 내용을 먼저 말하고, 이어서 예시나 계산 사례를 들어 설명하세요.
3. 절차가 있는 경우 ① ② ③ 순서로 단계별로 안내하세요.
4. 절세 포인트나 주의사항이 있으면 반드시 포함하세요.
5. 문서에서 특정 조항이나 규정을 인용할 때 답변 본문 안에 명시하세요 (예: "상속세 및 증여세법 제53조에 따르면...").
6. 답변 마지막에 반드시 다음 문구를 추가하세요:
   "📌 위 내용은 일반적인 세법 기준이며, 개인 상황에 따라 다를 수 있습니다. 정확한 사항은 세무사 또는 금융 전문가에게 확인하시길 권장합니다."

다음 경우에만 "RAG_INSUFFICIENT" 한 단어만 출력하세요:
- 참고 문서에 질문과 관련된 내용이 전혀 없는 경우

[참고 문서]
{context}

[질문]
{question}
"""

_GPT_FALLBACK_PROMPT = """
당신은 대한민국 자산 증여 전문 상담사입니다.
증여세법 및 관련 세법 지식을 바탕으로 질문에 답변하세요.

답변 작성 규칙:
1. 구체적인 금액·세율·기간·한도를 숫자로 명시하세요 (예: 10년간 2,000만 원, 세율 10~50%).
2. 핵심 내용을 먼저 말하고, 이어서 예시나 계산 사례를 들어 설명하세요.
3. 절차가 있는 경우 ① ② ③ 순서로 단계별로 안내하세요.
4. 절세 포인트나 주의사항이 있으면 반드시 포함하세요.
5. 답변 마지막에 반드시 다음 문구를 추가하세요:
   "📌 위 내용은 일반적인 세법 기준이며, 개인 상황에 따라 다를 수 있습니다. 정확한 사항은 세무사 또는 금융 전문가에게 확인하시길 권장합니다."

다음 경우에만 "GPT_INSUFFICIENT" 한 단어만 출력하세요:
- 질문이 증여와 전혀 관련 없는 경우
- 답변이 불가능할 정도로 개인적·구체적인 사례인 경우

[질문]
{question}
"""

_UNABLE_TO_ANSWER = (
    "죄송합니다. 해당 질문에 대해서는 정확한 답변을 드리기 어렵습니다. 😔\n\n"
    "더 정확한 도움을 받으시려면 **세무사** 또는 **금융 전문가**에게 문의해 주세요."
)

_WELCOME_MESSAGE = "안녕하세요! 👋 자녀 자산 증여에 관해 무엇이든 편하게 질문해 주세요 😊"

_QUICK_QUESTIONS = [
    "미성년자 자녀, 증여 공제 한도는 얼마일까?",
    "성인 자녀, 증여 공제 한도는 얼마일까?",
    "증여 꿀팁 알려주세요",
]


@st.cache_resource
def _load_vectorstore(pdf_path: str):
    loader = PyPDFLoader(pdf_path)
    docs = loader.load()
    splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
    splits = splitter.split_documents(docs)
    vectorstore = FAISS.from_documents(splits, OpenAIEmbeddings())
    return vectorstore


def _answer_with_rag(retriever, llm, question: str):
    """PDF RAG로 답변. 성공 시 (답변+출처 문자열, True), 문서 부족 시 (None, False)."""
    docs = retriever.invoke(question)
    context = "\n\n".join(d.page_content for d in docs)

    prompt = ChatPromptTemplate.from_messages([("user", _RAG_PROMPT)])
    chain = prompt | llm | StrOutputParser()
    response = chain.invoke({"context": context, "question": question})

    if "RAG_INSUFFICIENT" in response:
        return None, False

    # 페이지 번호 수집 (PyPDFLoader는 0-index → +1)
    pages = sorted(set(
        int(d.metadata.get("page", 0)) + 1
        for d in docs
        if d.metadata.get("page") is not None
    ))
    pdf_name = os.path.basename(_RAG_PDF_PATH)
    if pages:
        page_str = ", ".join(f"{p}p" for p in pages)
        source_line = f"\n\n📎 **출처:** {pdf_name} ({page_str})"
    else:
        source_line = f"\n\n📎 **출처:** {pdf_name}"

    return response + source_line, True


def _answer_with_gpt(llm, question: str):
    """GPT 자체 지식으로 fallback 답변. 성공 시 답변 문자열, 불가 시 None."""
    prompt = ChatPromptTemplate.from_messages([("user", _GPT_FALLBACK_PROMPT)])
    chain = prompt | llm | StrOutputParser()
    response = chain.invoke({"question": question})
    if "GPT_INSUFFICIENT" in response:
        return None
    return response

# ── Constants (kept in sync with app.py) ─────────────────────────────────────

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
    from collections import defaultdict
    counts: dict = defaultdict(lambda: [0, 0])
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
    concept_names = ", ".join(c["title"] for c in concepts[:6]) if concepts else "금융 기초 개념"
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


# ── Tab renderers ────────────────────────────────────────────────────────────

def _tab_learning(gs, concepts: list, history: list, badge_engine):
    name   = gs.character_name or "쏠쏠이"
    coins  = gs.coins
    world  = gs.world or "space"

    evolutions = CHAR_EVOLUTION.get(name, CHAR_EVOLUTION["쏠쏠이"])
    tier = 2 if coins >= 100 else (1 if coins >= 50 else 0)
    evo  = evolutions[tier]

    tc    = ["#fbbf24", "#a78bfa", "#818cf8"][tier]
    tglow = ["rgba(251,191,36,.6)", "rgba(167,139,250,.6)", "rgba(129,140,248,.7)"][tier]
    tbg   = ["rgba(251,191,36,.08)", "rgba(167,139,250,.1)", "rgba(129,140,248,.12)"][tier]
    stars = "⭐" * (tier + 1) + "✩" * (2 - tier)
    medal = ["🥉", "🥈", "🥇"][tier]

    dynamic_done = sum(
        1 for k, v in st.session_state.items()
        if isinstance(k, str) and k.startswith("dynamic_done_") and v
    )
    total_done = len(gs.completed_missions) + dynamic_done
    accuracy = (
        sum(1 for h in history if h.get("correct")) / len(history) * 100
        if history else 0
    )
    wko = {"space": "별빛 금융 은하", "dinosaur": "공룡 정글",
           "magic": "마법왕국", "ocean": "파도 저금섬"}.get(world, "핀퀘스트")
    tips = WORLD_FINANCIAL_TIPS.get(world, WORLD_FINANCIAL_TIPS["space"])

    st.markdown(
        f"""
        <style>
        @keyframes floatY {{ 0%,100%{{transform:translateY(0)}} 50%{{transform:translateY(-12px)}} }}
        @keyframes popIn  {{ from{{opacity:0;transform:scale(.8)}} to{{opacity:1;transform:scale(1)}} }}
        @keyframes pulse  {{ 0%,100%{{box-shadow:0 0 0 0 {tglow}}} 70%{{box-shadow:0 0 0 16px transparent}} }}
        .rv-hero {{ text-align:center; padding:20px 0 12px; animation:popIn .6s cubic-bezier(.34,1.56,.64,1); }}
        .rv-orb {{
            display:inline-flex; align-items:center; justify-content:center;
            width:120px; height:120px; border-radius:50%;
            background:radial-gradient(circle at 35% 35%, {tc}44, {tc}11);
            border:2px solid {tc}55;
            box-shadow:0 0 50px {tc}44;
            animation:floatY 3s ease-in-out infinite, pulse 2.5s ease-in-out infinite;
            font-size:4rem; margin:0 auto 14px;
        }}
        .rv-tier-badge {{
            display:inline-block; background:{tbg};
            border:1.5px solid {tc}66; border-radius:100px;
            padding:6px 20px; color:{tc}; font-size:.95rem; font-weight:900;
            margin-bottom:8px;
        }}
        .rv-bento {{ display:grid; grid-template-columns:1fr 1fr 1fr; gap:10px; margin:18px 0; }}
        .rv-box {{
            background:{tbg}; border:1px solid {tc}33; border-radius:18px;
            padding:18px 10px; text-align:center;
        }}
        .rv-num {{ font-size:1.8rem; font-weight:900; color:{tc}; line-height:1.2; }}
        .rv-lbl {{ font-size:.72rem; color:rgba(255,255,255,.5); margin-top:4px; letter-spacing:.3px; }}
        .rv-tip {{
            display:flex; align-items:flex-start; gap:10px;
            background:rgba(255,255,255,.05);
            border:1px solid rgba(255,255,255,.1);
            border-left:3px solid {tc};
            border-radius:0 14px 14px 0;
            padding:11px 14px; margin-bottom:8px;
            color:rgba(255,255,255,.82); font-size:.88rem; line-height:1.7;
        }}
        </style>
        <div class="rv-hero">
          <div class="rv-orb">{evo['emoji']}</div>
          <div class="rv-tier-badge">{evo['tier_name']}</div>
          <p style="color:rgba(255,255,255,.6);font-size:.88rem;margin:4px 0;">{evo['desc']}</p>
          <div style="font-size:1.5rem;letter-spacing:4px;margin:8px 0;">{stars}</div>
        </div>
        <div class="rv-bento">
          <div class="rv-box"><div class="rv-num">🪙 {coins}</div><div class="rv-lbl">모은 쏠코인</div></div>
          <div class="rv-box"><div class="rv-num">{total_done}</div><div class="rv-lbl">완료 미션</div></div>
          <div class="rv-box"><div class="rv-num">{accuracy:.0f}%</div><div class="rv-lbl">정답률</div></div>
        </div>
        <p style="color:white;font-size:.95rem;font-weight:800;margin:6px 0 12px;">📚 오늘 배운 금융 지식</p>
        {''.join(f'<div class="rv-tip"><span>💡</span><span>{t}</span></div>' for t in tips)}
        """,
        unsafe_allow_html=True,
    )

    if concepts:
        st.divider()
        st.markdown("#### 📖 오늘 배운 금융 개념")
        for c in concepts:
            st.markdown(
                f"""<div style="display:flex;align-items:center;gap:8px;
                    padding:7px 12px;margin-bottom:5px;
                    background:rgba(255,255,255,.06);border-radius:8px;border-left:3px solid {tc};">
                    <span style="font-size:1.3rem;">{c['emoji']}</span>
                    <div style="color:rgba(255,255,255,.9);"><b>{c['title']}</b>
                    {"<br><span style='font-size:0.82rem;color:rgba(255,255,255,.5);'>" + c['body'] + "</span>" if c['body'] else ""}
                    </div></div>""",
                unsafe_allow_html=True,
            )

    weak = _get_weak_concepts(history)
    if weak:
        st.divider()
        st.markdown("#### 🔁 다음엔 이 개념을 더 연습해요!")
        for w in weak:
            st.warning(f"💡 **{w}** — 한 번 더 도전해봐요!")

    if history:
        st.divider()
        chart = PortfolioChart()
        scores = chart.build_concept_scores(history)
        if any(v > 0 for v in scores.values()):
            st.markdown("#### 🧠 금융 개념 이해도 레이더")
            fig = chart.render_concept_radar(scores, gs.world or "ocean")
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


def _tab_badges(gs, badge_engine):
    from game.badge_engine import BADGES

    earned_ids = set(gs.badges)
    earned = [b for b in BADGES if b["id"] in earned_ids]
    unearned = [b for b in BADGES if b["id"] not in earned_ids]

    st.markdown("### 🏅 획득한 뱃지")
    if earned:
        cols = st.columns(4)
        for i, b in enumerate(earned):
            with cols[i % 4]:
                bdesc = b["desc"]
                bname = b["name"]
                bemoji = b["emoji"]
                st.markdown(
                    f'<div title="달성! {bdesc}" style="'
                    f'background:rgba(255,215,0,.12);border:2px solid rgba(255,215,0,.4);'
                    f'border-radius:16px;padding:14px 8px;text-align:center;cursor:default;">'
                    f'<div style="font-size:2rem;">{bemoji}</div>'
                    f'<div style="font-size:.78rem;font-weight:700;color:#fde68a;margin-top:6px;">{bname}</div>'
                    f'<div style="font-size:.68rem;color:rgba(255,255,255,.45);margin-top:3px;">{bdesc}</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
    else:
        st.info("아직 획득한 뱃지가 없어요. 미션을 완료해봐요! 🗺️")

    if unearned:
        st.divider()
        st.markdown("### 🎯 획득 가능한 뱃지")
        cols = st.columns(4)
        for i, b in enumerate(unearned):
            metrics = badge_engine._get_metrics(gs)
            current = metrics.get(b["type"], 0)
            pct = min(current / b["threshold"], 1.0) if b["threshold"] > 0 else 0
            how = _badge_how_to_earn(b)
            with cols[i % 4]:
                st.markdown(
                    f'<div title="{how}" style="'
                    f'background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.1);'
                    f'border-radius:16px;padding:14px 8px;text-align:center;cursor:default;'
                    f'filter:grayscale(80%);opacity:.7;">'
                    f'<div style="font-size:2rem;">{b["emoji"]}</div>'
                    f'<div style="font-size:.78rem;font-weight:700;color:rgba(255,255,255,.6);margin-top:6px;">{b["name"]}</div>'
                    f'<div style="font-size:.68rem;color:rgba(255,255,255,.35);margin-top:3px;">{how}</div>'
                    f'<div style="background:rgba(255,255,255,.1);border-radius:4px;margin-top:8px;height:4px;">'
                    f'<div style="background:#a78bfa;width:{pct*100:.0f}%;height:4px;border-radius:4px;"></div></div>'
                    f'<div style="font-size:.62rem;color:rgba(255,255,255,.3);margin-top:3px;">{current:.0f} / {b["threshold"]}</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

    total = len(BADGES)
    n_earned = len(earned)
    st.divider()
    st.markdown(f"**전체 뱃지 달성률:** {n_earned} / {total}  ({n_earned/total:.0%})")
    st.progress(n_earned / total)


def _badge_how_to_earn(b: dict) -> str:
    btype = b.get("type", "")
    thr = b.get("threshold", 0)
    mapping = {
        "missions_completed": f"미션 {thr}개 완료하기",
        "saving_missions":    f"저축 관련 미션 {thr}개 완료",
        "invest_missions":    f"투자 관련 미션 {thr}개 완료",
        "budget_missions":    f"용돈 관련 미션 {thr}개 완료",
        "interest_missions":  f"이자 관련 미션 {thr}개 완료",
        "accuracy":           f"정답률 {thr}% 이상 달성",
        "worlds_visited":     f"{thr}개 이상의 세계에서 미션 완료",
        "coins":              f"쏠코인 {thr}개 이상 보유",
    }
    return mapping.get(btype, b.get("desc", ""))


def _tab_products(gs, concepts: list, generator):
    st.markdown("### 👨‍👩‍👧 부모님께 드리는 맞춤 안내")

    # ── 자산 증여 상담 챗봇 ───────────────────────────────────────────────────
    st.markdown(
        """
        <div style="margin:4px 0 20px;text-align:center;">
          <div style="display:inline-block;background:rgba(168,85,247,.12);border:1px solid rgba(168,85,247,.3);
                      border-radius:100px;padding:5px 16px;color:#a855f7;font-size:.76rem;font-weight:700;
                      letter-spacing:1.2px;margin-bottom:14px;">✦ 부모님 전용 ✦</div>
          <div style="font-size:2.2rem;margin-bottom:8px;">💸</div>
          <h3 style="font-size:1.35rem;font-weight:900;letter-spacing:-.4px;margin:0 0 8px;">
            자산 증여 상담 챗봇
          </h3>
          <p style="font-size:.9rem;color:#6b7280;margin:0;">
            자녀에게 자산을 증여할 때 궁금한 점을 편하게 물어보세요
          </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    GIFT_CHAT_KEY = "gift_chat_history"
    GIFT_QUICK_KEY = "_gift_quick_question"
    GIFT_SHOW_QUICK_KEY = "_gift_show_quick"

    # 초기화
    if GIFT_CHAT_KEY not in st.session_state:
        st.session_state[GIFT_CHAT_KEY] = [
            {"role": "assistant", "content": _WELCOME_MESSAGE}
        ]
    if GIFT_QUICK_KEY not in st.session_state:
        st.session_state[GIFT_QUICK_KEY] = None
    if GIFT_SHOW_QUICK_KEY not in st.session_state:
        st.session_state[GIFT_SHOW_QUICK_KEY] = True

    # RAG 엔진 로드
    rag_error = None
    _llm = None
    _retriever = None
    try:
        with st.spinner("📄 증여 문서를 불러오는 중..."):
            _llm = ChatOpenAI(temperature=0.2, model="gpt-4o-mini", max_tokens=1200)
            _vs = _load_vectorstore(_RAG_PDF_PATH)
            _retriever = _vs.as_retriever(search_type="similarity", search_kwargs={"k": 4})
    except Exception as _e:
        rag_error = str(_e)

    if rag_error:
        st.warning(f"⚠️ RAG 문서 로드 실패 — 기본 GPT 모드로 동작합니다.\n`{rag_error}`")

    # 채팅 히스토리 출력
    chat_history = st.session_state[GIFT_CHAT_KEY]
    for msg in chat_history:
        is_user = msg["role"] == "user"
        if is_user:
            bubble_style = "background:#eff6ff;border:1px solid #bfdbfe;margin-left:auto;text-align:right;"
            icon, text_color = "👤", "#1e40af"
        else:
            bubble_style = "background:#f5f3ff;border:1px solid #ddd6fe;"
            icon, text_color = "🤖", "#5b21b6"
        st.markdown(
            f'<div style="{bubble_style}border-radius:18px;padding:12px 16px;'
            f'margin-bottom:10px;max-width:85%;font-size:.9rem;'
            f'color:{text_color};line-height:1.7;">'
            f'<span style="font-size:.75rem;opacity:.6;">{icon}</span><br>'
            f'{msg["content"].replace(chr(10), "<br>")}</div>',
            unsafe_allow_html=True,
        )

    # 빠른 질문 버튼
    if st.session_state[GIFT_SHOW_QUICK_KEY]:
        st.markdown("##### 💬 이런 것들이 궁금하신가요?")
        q_cols = st.columns(len(_QUICK_QUESTIONS))
        for i, (col, question) in enumerate(zip(q_cols, _QUICK_QUESTIONS)):
            with col:
                if st.button(question, key=f"gift_quick_{i}", use_container_width=True):
                    st.session_state[GIFT_QUICK_KEY] = question
                    st.session_state[GIFT_SHOW_QUICK_KEY] = False
                    st.rerun()

    st.markdown("<div style='margin-top:16px;'></div>", unsafe_allow_html=True)

    # 입력창
    counter = st.session_state.get("_gift_q_counter", 0)
    user_q = st.text_input(
        "질문 입력",
        placeholder="예) 미성년 자녀에게 증여세 없이 줄 수 있는 한도가 얼마예요?",
        label_visibility="collapsed",
        key=f"gift_chat_q_{counter}",
    )
    col_send, col_clear = st.columns([4, 1])
    with col_send:
        send_clicked = st.button("💬 보내기", use_container_width=True, type="primary", key="gift_send")
    with col_clear:
        clear_clicked = st.button("🗑️", use_container_width=True, key="gift_clear")

    if clear_clicked:
        st.session_state[GIFT_CHAT_KEY] = [
            {"role": "assistant", "content": _WELCOME_MESSAGE}
        ]
        st.session_state[GIFT_QUICK_KEY] = None
        st.session_state[GIFT_SHOW_QUICK_KEY] = True
        st.session_state["_gift_q_counter"] = counter + 1
        st.rerun()

    # 질문 처리 (직접 입력 or 빠른 버튼)
    pending_q = None
    if send_clicked and user_q.strip():
        pending_q = user_q.strip()
        st.session_state[GIFT_SHOW_QUICK_KEY] = False
        st.session_state["_gift_q_counter"] = counter + 1
    elif st.session_state[GIFT_QUICK_KEY]:
        pending_q = st.session_state[GIFT_QUICK_KEY]
        st.session_state[GIFT_QUICK_KEY] = None

    if pending_q:
        st.session_state[GIFT_CHAT_KEY].append({"role": "user", "content": pending_q})
        ai_reply = _UNABLE_TO_ANSWER

        try:
            if _retriever is not None and _llm is not None:
                # Stage 1: PDF RAG + 출처
                with st.spinner("📄 문서에서 답변을 찾는 중..."):
                    rag_answer, rag_ok = _answer_with_rag(_retriever, _llm, pending_q)

                if rag_ok:
                    ai_reply = rag_answer
                else:
                    # Stage 2: GPT fallback
                    with st.spinner("🤖 추가 지식으로 답변을 생성하는 중..."):
                        gpt_answer = _answer_with_gpt(_llm, pending_q)
                    if gpt_answer is not None:
                        ai_reply = gpt_answer
            else:
                # RAG 로드 실패 시 직접 GPT 호출
                from openai import OpenAI as _OAI
                _cli = _OAI()
                _msgs = [{"role": m["role"], "content": m["content"]}
                         for m in st.session_state[GIFT_CHAT_KEY]]
                _resp = _cli.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=_msgs,
                    max_tokens=1200,
                    temperature=0.2,
                )
                ai_reply = _resp.choices[0].message.content
        except Exception as e:
            ai_reply = f"⚠️ 오류가 발생했어요: {e}"

        st.session_state[GIFT_CHAT_KEY].append({"role": "assistant", "content": ai_reply})
        st.rerun()

    st.divider()

    # ── AI report ──────────────────────────────────────────────────────────────
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
    missions  = _load_missions()
    concepts  = _get_learned_concepts(gs, missions)
    history   = st.session_state.get("_answer_history", [])

    tab1, tab2, tab3 = st.tabs(
        ["📚 오늘의 학습", "🏅 뱃지 & 성취", "💳 금융상품 안내"]
    )

    with tab1:
        _tab_learning(gs, concepts, history, badge_engine)

    with tab2:
        _tab_badges(gs, badge_engine)

    with tab3:
        _tab_products(gs, concepts, scenario_generator)
