# 핀퀘스트 (FinQuest)

어린이 금융 교육 Phaser 3 게임 — Streamlit으로 구동

---

## 설치

```bash
pip install -r requirements.txt
```

## 환경변수 설정

```bash
cp .env.example .env
# .env 파일 열고 아래 입력:
# OPENAI_API_KEY=sk-...
```

API 키 없이도 실행 가능 — 기본(정적) 미션으로 자동 폴백됩니다.

## 실행

```bash
streamlit run app.py
```

브라우저가 자동으로 열리지 않으면 `http://localhost:8501` 접속

---

## 게임 방법

| 조작 | 방법 |
|------|------|
| 이동 | 방향키 `↑ ↓ ← →` 또는 `W A S D` |
| 모바일 | 화면 좌측 하단 D-pad 버튼 |
| 게임 종료 | `ESC` 키 |

1. **온보딩** — 세계(공룡 정글 / 우주 정거장 / 마법 왕국 / 심해 왕국)와 캐릭터 설정
2. **탐험** — 캐릭터를 이동해 금코인을 수집
3. **퀴즈** — 악당 NPC와 충돌(또는 접근)하면 금융 퀴즈 시작
   - ⚡ 순찰형 — 일정 경로 왕복, 기초 퀴즈 (충돌 trigger)
   - 🔥 추적형 — 200 px 이내 접근 시 추격, 중급 퀴즈 (충돌 trigger)
   - 💀 보스 — 맵 중앙 고정, 72 px 이내 접근 시 심화 퀴즈 (proximity trigger)
4. **보스 처치** → 세계 클리어 연출 → 부모 리포트 확인
5. **`ESC`** → 언제든 종료 후 부모 리포트 확인

---

## 기술 스택

| 레이어 | 기술 |
|--------|------|
| 게임 엔진 | Phaser 3.60 (CDN, HTML5 Canvas) |
| 웹 앱 | Streamlit (Python) |
| AI 퀴즈 | OpenAI GPT-4o-mini |
| RAG | scikit-learn TF-IDF |
| ML 난이도 추천 | scikit-learn KNN |
| 시각화 | Plotly |
| 컴포넌트 통신 | `components.declare_component` (양방향 postMessage) |

---

## 발표용 시연 순서

1. 온보딩: **우주 정거장** 선택, 이름 입력 → "탐험 시작!"
2. 방향키로 캐릭터 이동 → 금코인 수집 (파티클 이펙트 확인)
3. 순찰형 NPC(외계인) 충돌 → AI 퀴즈 확인 → 정답 (카메라 흔들림 + 처치 이펙트)
4. 보스(블랙홀)에 접근 → 심화 퀴즈 → 정답 → 클리어 연출(플래시 + 별 파티클)
5. 부모 리포트 4개 탭 순서대로 설명
   - 📚 오늘의 학습: 개념 목록 + 레이더 차트
   - 📈 자산 성장: 코인 히스토리 + 복리 시뮬레이션
   - 🏅 뱃지 & 성취: 배지 현황
   - 💳 금융상품 안내: AI 맞춤 리포트 + 상품 카드

---

## 프로젝트 구조

```
finquest/
├── app.py                          # 메인 라우터
├── data/
│   ├── missions.json               # 정적 퀴즈 24개
│   └── worlds.json                 # 세계 & 구역 정의
├── components/
│   └── phaser_game/
│       ├── __init__.py             # declare_component 래퍼
│       └── frontend/index.html    # Phaser 3 게임 (NPC 3종, 파티클)
├── game/
│   ├── state.py                    # GameState (session_state 래퍼)
│   ├── badge_engine.py             # 뱃지 판정
│   └── phaser_builder.py          # 퀴즈 AI 프리로드
├── ai/
│   ├── rag_engine.py              # TF-IDF RAG
│   ├── quiz_generator.py          # OpenAI 퀴즈 생성
│   └── scenario_generator.py     # 미션 + 부모 리포트 생성
├── pages/
│   └── parent_report.py           # 4탭 부모 리포트
└── ui/
    └── portfolio_chart.py         # Plotly 차트 모음
```
# soladventure
