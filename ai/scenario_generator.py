from __future__ import annotations

import json
import os

import streamlit as st

from ai.rag_engine import RAGEngine

SYSTEM_PROMPT = """너는 어린이 금융 교육 게임 "핀퀘스트"의 미션 생성 AI야.
주어진 세계와 금융 개념을 바탕으로 아이들이 즐겁게 배울 수 있는 미션을 만들어줘.

규칙:
- 투자 수익 보장, 원금 손실 가능성 과장 표현 절대 금지
- 특정 금융상품 가입 권유 금지 (정보 제공만)
- 연령에 맞는 쉬운 언어 사용
- 세계 테마에 맞는 캐릭터와 배경으로 스토리 구성
- 반드시 JSON만 반환 (다른 텍스트 없음)

반환 형식:
{
  "question": "미션 질문 (캐릭터 이름 포함, 50자 이상)",
  "choices": [
    {"id": "a", "text": "선택지", "coins": 정수, "correct": false, "feedback": "피드백"},
    {"id": "b", "text": "선택지", "coins": 정수, "correct": true,  "feedback": "피드백"},
    {"id": "c", "text": "선택지", "coins": 정수, "correct": false, "feedback": "피드백"}
  ],
  "concept_card": {
    "title": "핵심 개념 이름",
    "body": "한 문장 설명 (아이 눈높이)",
    "emoji": "이모지"
  }
}"""

WORLD_LABELS = {
    "dinosaur": "공룡 정글 (캐릭터: 브라키, 트리케라, 스테고 같은 공룡)",
    "space": "우주 탐험 (캐릭터: 우주 탐험가, 로봇)",
    "magic": "마법 왕국 (캐릭터: 마법사, 요정)",
    "ocean": "해저 왕국 (캐릭터: 물고기, 해마, 문어)",
}

AGE_LABELS = {
    "young": "6~8세 어린이 (매우 쉬운 언어, 비유 위주)",
    "middle": "9~11세 초등학생 (간단한 계산 포함 가능)",
    "all": "12~13세 고학년 (기본 수식·퍼센트 사용 가능)",
}


class ScenarioGenerator:
    def __init__(self, rag_engine: RAGEngine):
        self.rag = rag_engine
        self._client = None

    def _get_client(self):
        if self._client is not None:
            return self._client
        api_key = (
            st.session_state.get("openai_api_key")
            or os.environ.get("OPENAI_API_KEY")
        )
        if not api_key:
            return None
        try:
            from openai import OpenAI
            self._client = OpenAI(api_key=api_key)
            return self._client
        except Exception:
            return None

    # ── Mission generation ───────────────────────────────────────────────────

    def generate_mission(
        self,
        world: str,
        zone_id: str,
        age_group: str,
        completed_count: int,
        character_name: str,
    ) -> dict | None:
        client = self._get_client()
        if not client:
            return None

        context = self.rag.get_context_for_prompt(world, zone_id, age_group)
        difficulty_hint = (
            "쉬운 수준" if completed_count < 2 else
            "보통 수준" if completed_count < 5 else
            "심화 수준"
        )

        user_prompt = (
            f"세계: {WORLD_LABELS.get(world, world)}\n"
            f"구역 ID: {zone_id}\n"
            f"연령: {AGE_LABELS.get(age_group, age_group)}\n"
            f"탐험가 이름: {character_name}\n"
            f"완료한 미션 수: {completed_count} (난이도 힌트: {difficulty_hint})\n\n"
            f"관련 금융 개념:\n{context}\n\n"
            f"위 정보를 바탕으로 {character_name}이(가) 등장하는 재미있는 미션을 JSON으로 만들어줘. "
            f"정답은 반드시 1개여야 하고 coins 값은 -20~+20 범위로 설정해."
        )

        try:
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                max_tokens=1000,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
            )
            raw = response.choices[0].message.content
            data = json.loads(raw)
            return self._validate_mission(data)
        except Exception:
            return None

    def _validate_mission(self, data: dict) -> dict | None:
        required = {"question", "choices", "concept_card"}
        if not required.issubset(data.keys()):
            return None
        if len(data["choices"]) < 2:
            return None
        if not any(c.get("correct") for c in data["choices"]):
            return None
        for c in data["choices"]:
            if "id" not in c:
                c["id"] = chr(96 + data["choices"].index(c) + 1)
            if "coins" not in c:
                c["coins"] = 10 if c.get("correct") else -5
        return data

    # ── Parent report ────────────────────────────────────────────────────────

    def generate_parent_report(self, game_state, recommender) -> str:
        client = self._get_client()
        accuracy = recommender.get_accuracy()
        concept_stats = recommender.concept_accuracy()

        weak_concepts = [
            c for c, s in concept_stats.items() if s["total"] > 0 and s["correct"] / s["total"] < 0.6
        ]
        strong_concepts = [
            c for c, s in concept_stats.items() if s["total"] > 0 and s["correct"] / s["total"] >= 0.8
        ]

        if not client:
            return self._static_report(
                game_state, accuracy, weak_concepts, strong_concepts, concept_stats
            )

        summary = (
            f"아이 이름: {game_state.character_name}\n"
            f"선택 세계: {game_state.world}\n"
            f"완료 미션 수: {len(game_state.completed_missions)}\n"
            f"획득 코인: {game_state.coins}\n"
            f"전체 정답률: {accuracy:.0%}\n"
            f"잘한 개념: {', '.join(strong_concepts) if strong_concepts else '없음'}\n"
            f"취약 개념: {', '.join(weak_concepts) if weak_concepts else '없음'}\n"
        )

        try:
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                max_tokens=800,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "너는 어린이 금융 교육 전문가야. "
                            "부모님께 아이의 학습 결과를 따뜻하고 구체적으로 설명해줘. "
                            "취약 개념에 대한 가정에서의 대화 팁도 포함해줘. "
                            "금융상품 가입 권유는 절대 하지 마."
                        ),
                    },
                    {
                        "role": "user",
                        "content": f"아이 학습 데이터:\n{summary}\n\n부모님께 드리는 리포트를 작성해줘.",
                    },
                ],
            )
            return response.choices[0].message.content
        except Exception:
            return self._static_report(
                game_state, accuracy, weak_concepts, strong_concepts, concept_stats
            )

    def _static_report(
        self,
        game_state,
        accuracy: float,
        weak: list,
        strong: list,
        stats: dict,
    ) -> str:
        lines = [
            f"📊 **{game_state.character_name}의 핀퀘스트 학습 리포트**\n",
            f"- 완료 미션: {len(game_state.completed_missions)}개",
            f"- 획득 코인: {game_state.coins}코인",
            f"- 전체 정답률: {accuracy:.0%}\n",
        ]
        if strong:
            lines.append(f"✅ **잘 이해한 개념:** {', '.join(strong)}")
        if weak:
            lines.append(f"💡 **더 연습이 필요한 개념:** {', '.join(weak)}")
            lines.append("\n📝 **가정에서 대화해보세요:**")
            for c in weak[:2]:
                lines.append(f'- "{c}에 대해 오늘 게임에서 배웠는데, 어떤 내용이었어?" 라고 물어봐 주세요.')
        lines.append(
            "\n💰 **금융 교육 팁:** 용돈을 직접 관리하게 해주시면 더 빠르게 이해할 수 있어요!"
        )
        return "\n".join(lines)
