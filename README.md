# 신한 쏠어드벤쳐 — 어린이 금융 탐험

> 금융 지식으로 악당을 물리치는 어린이 경제교육 게임 · Streamlit + Phaser 3

---

## 주요 기능

| 기능 | 설명 |
|------|------|
| 🎮 **Phaser 3 게임** | 방향키로 캐릭터를 이동하며 악당 NPC와 금융 퀴즈 배틀 |
| 🤖 **AI 퀴즈 생성** | GPT-4o-mini가 나이·세계관에 맞는 3지선다 퀴즈를 실시간 생성 |
| 📰 **어린이 뉴스** | 실시간 RSS → **KoBERT 적합성 필터** → GPT 어린이용 요약 |
| 🧠 **KoBERT 필터** | ELS·레버리지·공매도 등 성인 기사를 자동 차단, 적합 기사만 노출 |
| 📊 **부모 리포트** | 학습 개념·코인 히스토리·배지·금융상품 추천 4탭 리포트 |
| 💰 **용돈 기입장** | 수입·지출 기록 및 잔액 관리 |
| 🐷 **저축 목표** | 목표 금액 설정 및 달성률 추적 |
| 📖 **금융 단어장** | 오늘의 금융 개념 카드 |
| 📲 **엄마 조르기** | NCP SMS API로 부모에게 용돈 요청 메시지 발송 |
| 🏦 **금융상품 추천** | 나이·목표별 맞춤 금융상품 안내 |

---

## 설치 및 실행

```bash
# 1. 패키지 설치
pip install -r requirements.txt

# 2. 환경변수 설정
cp .env.example .env
# .env 에 아래 값 입력
# OPENAI_API_KEY=sk-...

# 3. 실행
streamlit run app.py
```

브라우저에서 `http://localhost:8501` 접속

---

## 환경변수

| 변수 | 필수 | 설명 |
|------|------|------|
| `OPENAI_API_KEY` | ✅ | GPT-4o-mini 퀴즈·요약 생성 |

> API 키 없이도 실행 가능 — 정적 미션으로 자동 폴백됩니다.

---

## 게임 방법

**온보딩** (4단계)
1. 캐릭터 선택 — 쏠쏠이 / 몰리 / 쏠리
2. 나이 선택 — 7~9세 / 10~12세 / 13세 이상
3. 세계 선택 — 별빛 금융 은하 🚀 / 파도 저금섬 🐋 / 용돈 마법왕국 ✨
4. 모험 시작!

**게임 조작**

| 조작 | 방법 |
|------|------|
| 이동 | 방향키 `↑ ↓ ← →` 또는 `W A S D` |
| 모바일 | 화면 좌측 하단 D-pad |

**NPC 유형**

| 유형 | 특징 | 퀴즈 |
|------|------|------|
| ⚡ 순찰형 | 일정 경로 왕복 | 기초 |
| 🔥 추적형 | 200px 이내 접근 시 추격 | 중급 |
| 💀 보스 | 맵 중앙 고정 | 심화 |

---

## 어린이 뉴스 파이프라인

```
실시간 RSS 수집
(매일경제 · 한국경제)
       ↓
KoBERT 어린이 적합성 필터
(maninglearchine/kobert-article-classifier)
       ↓  부적절 차단 (ELS·레버리지·공매도 등)
GPT-4o-mini 어린이용 요약
       ↓
뉴스 카드 + AI 퀴즈 생성
```

KoBERT 모델은 HuggingFace에서 자동 다운로드되며, 앱 시작 시 1회만 로드됩니다.
모델 로드 실패 시 필터 없이 전체 기사를 통과시키는 fallback으로 동작합니다.

---

## 기술 스택

| 레이어 | 기술 |
|--------|------|
| 게임 엔진 | Phaser 3.60 (HTML5 Canvas) |
| 웹 프레임워크 | Streamlit |
| AI 퀴즈·요약 | OpenAI GPT-4o-mini |
| 뉴스 필터 | KoBERT (`klue/bert-base` 파인튜닝) |
| RAG | LangChain + FAISS |
| 난이도 추천 | scikit-learn KNN |
| 알림 | NCP SMS API |
| 시각화 | Plotly |

---

## 프로젝트 구조

```
soladventure/
├── app.py                      # 메인 라우터 · 온보딩 · 게임 화면
├── requirements.txt
├── progress.json               # 로컬 게임 진행 상태 저장
│
├── ai/
│   ├── news_crawler.py         # RSS 수집 + KoBERT 필터 + GPT 요약
│   ├── quiz_generator.py       # GPT-4o-mini 퀴즈 생성
│   ├── scenario_generator.py   # 미션·부모 리포트 생성
│   ├── rag_engine.py           # LangChain + FAISS RAG
│   ├── recommender.py          # KNN 난이도 추천
│   └── finance_docs.py         # 금융 교육 문서
│
├── game/
│   ├── state.py                # GameState (session_state 래퍼)
│   ├── badge_engine.py         # 배지 판정 엔진
│   ├── phaser_builder.py       # 퀴즈 프리로드
│   ├── map_engine.py           # 맵 생성
│   └── persistence.py          # 진행상태 저장·불러오기
│
├── components/
│   └── phaser_game/            # Phaser 3 Streamlit 컴포넌트
│
├── pages/
│   └── parent_report.py        # 부모 리포트 (4탭)
│
├── ui/
│   ├── components.py           # 공통 UI 컴포넌트
│   ├── animations.py           # 레벨업·배지 애니메이션
│   └── portfolio_chart.py      # Plotly 차트
│
├── mcp_servers/
│   └── ncp_sms_server.py       # NCP SMS MCP 서버
│
├── data/
│   ├── missions.json           # 정적 퀴즈
│   └── worlds.json             # 세계·구역 정의
│
├── assets/                     # 캐릭터 이미지
├── music/                      # BGM
└── static/                     # 정적 파일
```

---

## 라이선스

MIT
