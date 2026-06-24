"""
OpenAI 기반 퀴즈 생성기 — 실패 시 missions.json으로 폴백
"""
import json
import os
import random

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

WORLD_CONCEPTS = {
    "dinosaur": {"patrol": "저축",           "chaser": "용돈 관리",   "boss": "투자"},
    "space":    {"patrol": "주식이란?",       "chaser": "주식 투자",   "boss": "주식 시장"},
    "magic":    {"patrol": "예산",           "chaser": "소비 습관",   "boss": "복리"},
    "ocean":    {"patrol": "보험",           "chaser": "부채 관리",   "boss": "세금"},
}

ENEMY_NAMES = {
    "dinosaur": {"patrol": "랩터",   "chaser": "티렉스",   "boss": "메가로돈"},
    "space":    {"patrol": "외계인", "chaser": "전투 로봇", "boss": "블랙홀"},
    "magic":    {"patrol": "고블린", "chaser": "마녀",      "boss": "드래곤"},
    "ocean":    {"patrol": "복어",   "chaser": "상어",      "boss": "크라켄"},
}

DIFF_DESC = {
    "easy":   "기초 수준 (O/X 또는 단순 3지선다, 매우 짧은 문장)",
    "medium": "중급 수준 (개념 적용 3지선다, 예시 활용)",
    "hard":   "심화 수준 (개념 응용 3지선다 — 수학적 계산 문제 절대 금지)",
}

WORLD_KO = {
    "dinosaur": "공룡 정글",
    "space":    "별빛 금융 은하",
    "magic":    "용돈 마법왕국",
    "ocean":    "파도 저금섬",
}


class QuizGenerator:
    """Generate quizzes with OpenAI GPT-4o-mini; falls back to missions.json."""

    def __init__(self):
        import streamlit as st
        key = st.session_state.get("openai_api_key") or os.environ.get("OPENAI_API_KEY")
        self._client = None
        if key:
            try:
                from openai import OpenAI
                self._client = OpenAI(api_key=key)
            except ImportError:
                pass

        self._rag = None
        try:
            from ai.rag_engine import RAGEngine
            self._rag = RAGEngine()
        except Exception:
            pass

        self._fallback: list = []
        try:
            path = os.path.join(BASE_DIR, "data", "missions.json")
            with open(path, encoding="utf-8") as f:
                self._fallback = json.load(f)["missions"]
        except Exception:
            pass

    # ── Public API ───────────────────────────────────────────────────────────

    def generate_quiz(
        self,
        world: str,
        difficulty: str,
        age_group: str,
        character_name: str,
        enemy_type: str,
    ) -> dict:
        concept     = WORLD_CONCEPTS.get(world, {}).get(enemy_type, "저축")
        enemy_name  = ENEMY_NAMES.get(world, {}).get(enemy_type, "악당")

        if self._client:
            try:
                return self._openai_quiz(
                    world, concept, difficulty, age_group, character_name, enemy_name
                )
            except Exception:
                pass

        return self._fallback_quiz(world, difficulty)

    # ── OpenAI generation ────────────────────────────────────────────────────

    def _openai_quiz(self, world, concept, difficulty, age_group, character_name, enemy_name):
        context = ""
        if self._rag:
            try:
                context = self._rag.get_context_for_prompt(world, concept, age_group)
            except Exception:
                pass

        world_ko  = WORLD_KO.get(world, world)
        diff_desc = DIFF_DESC.get(difficulty, "3지선다")

        _AGE_LABEL = {
            "young":       "초등학교 저학년(7~9세) — 매우 간단한 단어, 짧은 문장, 계산 문제 금지",
            "middle":      "초등학교 고학년(10~12세) — 일상적인 금융 용어 가능, 계산 문제 금지",
            "senior":      "초등학교 고학년(10~12세) — 일상적인 금융 개념 적용, 계산 문제 금지",
            "elementary":  "초등학생(7~12세) — 쉬운 언어와 예시 활용, 계산 문제 금지",
        }
        age_label = _AGE_LABEL.get(age_group, "초등학생 — 쉬운 언어, 계산 문제 금지")

        stock_rule = (
            "\n- 주식·투자 관련 개념(주식이란, 주가, 배당, 분산투자, 주식 시장 등)을 어린이 눈높이로 설명할 것"
            if world == "space" else ""
        )
        system = f"""너는 어린이 금융 교육 게임 "핀퀘스트"의 퀴즈 생성 AI야.
{character_name}이(가) {world_ko}에서 {enemy_name}을(를) 만났어!

규칙:
- 투자 수익 보장 표현 절대 금지
- 수학적 계산이 필요한 문제 절대 금지 (덧셈·뺄셈·퍼센트 계산·금액 비교 등 모두 금지)
- 반드시 아래 핵심 개념 주제로만 질문 생성: {concept}
- 대상 연령: {age_label}
- 질문 안에 "{world_ko}" 배경과 "{enemy_name}" 캐릭터를 자연스럽게 포함
- 반드시 JSON만 반환 (마크다운 코드블록 없음)
- 난이도: {diff_desc}
- choices 배열: 정답 1개 포함 3개 선택지 (순서를 랜덤하게 섞어)
- coins: 정답=15, 오답=-5{stock_rule}

{f"참고 금융 개념:{chr(10)}{context}" if context else f"핵심 개념: {concept}"}

JSON 형식:
{{
  "question": "질문 (1~2문장, 세계 배경 포함)",
  "choices": [
    {{"id":"a","text":"선택지 텍스트","correct":true,"feedback":"왜 맞는지 한 문장","coins":15}},
    {{"id":"b","text":"선택지 텍스트","correct":false,"feedback":"왜 틀렸는지","coins":-5}},
    {{"id":"c","text":"선택지 텍스트","correct":false,"feedback":"왜 틀렸는지","coins":-5}}
  ],
  "concept_card": {{
    "title": "오늘의 금융 개념: {concept}",
    "body": "핵심 한 줄 설명 (어린이 눈높이)",
    "emoji": "관련 이모지"
  }}
}}"""

        resp = self._client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system.strip()},
                {"role": "user",   "content": (
                    f"world={world}, concept={concept}, difficulty={difficulty}, "
                    f"enemy={enemy_name}, character={character_name}"
                )},
            ],
            max_tokens=900,
            response_format={"type": "json_object"},
        )
        data = json.loads(resp.choices[0].message.content)
        self._validate(data)
        return data

    @staticmethod
    def _validate(data: dict):
        assert "question" in data, "question missing"
        assert "choices" in data and len(data["choices"]) >= 2, "choices missing"
        assert any(c.get("correct") for c in data["choices"]), "no correct answer"

    # ── Fallback ─────────────────────────────────────────────────────────────

    def _fallback_quiz(self, world: str, difficulty: str) -> dict:
        import streamlit as st
        pool = [m for m in self._fallback if world in m.get("id", "")]
        if not pool:
            pool = self._fallback
        if pool:
            shown = st.session_state.get("_fallback_shown_ids", [])
            shown_set = set(shown)
            unseen = [m for m in pool if m.get("id", "") not in shown_set]
            if not unseen:
                st.session_state["_fallback_shown_ids"] = []
                unseen = pool
            m = random.choice(unseen)
            mid = m.get("id", "")
            st.session_state["_fallback_shown_ids"] = (shown + [mid])[-50:]
            return {
                "question":    m.get("question", "저축이란 무엇일까요?"),
                "choices":     m.get("choices", []),
                "concept_card": m.get("concept_card", {
                    "title": "금융 개념", "body": "금융 지식을 쌓아요!", "emoji": "💰",
                }),
            }
        return {
            "question": "저축이 왜 중요할까요?",
            "choices": [
                {"id":"a","text":"미래를 위해 돈을 모을 수 있어요","correct": True,
                 "feedback":"정답! 저축은 미래를 위한 준비예요.","coins": 15},
                {"id":"b","text":"지금 바로 쓰기 위해서요","correct": False,
                 "feedback":"저축은 지금 쓰는 게 아니에요.","coins": -5},
                {"id":"c","text":"부모님께 보여주려고요","correct": False,
                 "feedback":"그건 저축의 목적이 아니에요.","coins": -5},
            ],
            "concept_card": {
                "title": "저축", "body": "미래를 위해 지금 돈을 아껴 모으는 것", "emoji": "🐷",
            },
        }
