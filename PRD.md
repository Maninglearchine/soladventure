# 신한 키즈 금융 놀이터 — PRD (Product Requirements Document)


---

## 1. 서비스 개요

| 항목 | 내용 |
|------|------|
| **서비스명** | 신한 키즈 금융 놀이터 |
| **앱 내 명칭** | 신한 쏠어드벤쳐 |
| **서비스 형태** | 어린이 금융 교육 게임 (웹 앱) |
| **대상 사용자** | 7세 이상 어린이 및 보호자 |
| **핵심 기술** | Python / Streamlit, Phaser 3, GPT-4o-mini, KoBERT, LangChain |
| **진입점** | `app.py` (3,054줄) |

### 핵심 가치 제안

어린이가 RPG 게임 방식으로 퀴즈를 풀며 저축·투자·소비 등 금융 개념을 자연스럽게 학습하고, 보호자에게 학습 리포트·맞춤 금융 상품 정보·증여 상담 챗봇을 제공한다.

---

## 2. 사용자 유형

| 유형 | age_group | 설명 | 주요 접근 기능 |
|------|-----------|------|---------------|
| **어린이 저학년** | `young` (7~9세) | 초등 1~3학년 | 쉬운 언어 퀴즈, 저축·용돈 위주 |
| **어린이 고학년** | `middle` (10~12세) | 초등 4~6학년 | 일반 금융 용어 포함 퀴즈 |
| **중학생 이상** | `senior` (13세~) | 중학생 이상 | 뉴스 AI 요약 + 뉴스 퀴즈, 심화 개념 |
| **보호자 (부모)** | — | 간접 사용자 | 학습 리포트, 증여 상담 챗봇, 금융 상품 안내 |

---

## 3. 핵심 기능 명세

### 3.1 온보딩 (4단계)

✅ **구현 완료**

| 단계 | 화면명 | 내용 |
|------|--------|------|
| Step 0 | 캐릭터 선택 | 쏠쏠이(⭐), 몰리(🌸), 쏠리(🌊) 중 1 선택 + 캐릭터 이미지 표시 |
| Step 1 | 나이 설정 | young(7~9살) / middle(10~12살) / senior(13살 이상) 선택 |
| Step 2 | 세계 선택 | 별빛 금융 은하(우주·투자) / 파도 저금섬(해양·이자) / 용돈 마법왕국(마법·소비) |
| Step 3 | 인트로 | 캐릭터 입장 애니메이션 + 탐험 시작 메시지 |

- 각 단계는 `intro_step` session_state로 관리
- 온보딩 완료 시 `map` 페이지로 전환

---

### 3.2 게임 맵 및 미션 시스템

✅ **구현 완료**

**세계(World) & 구역(Zone) 구성** (`data/worlds.json` 기반)

| 세계 ID | 한국어명 | 핵심 개념 | 구역 3개 |
|---------|---------|---------|---------|
| `space` | 별빛 금융 은하 | 투자·리스크 | 투자 행성, 위험 소행성, 분산 은하 |
| `ocean` | 해저 왕국 | 이자·복리 | 이자 산호초, 복리 해구, 장기 저축 궁전 |
| `magic` | 마법 왕국 | 용돈·소비 판단 | 예산 성, 필요 vs 욕구 시장, 충동 구매 동굴 |
| `dinosaur` | 공룡 정글 | 저축·목표 설정 | 저축 동굴, 목표 나무, 물물교환 시장 |

> `dinosaur` 세계는 `worlds.json`에 데이터 존재하나, 온보딩 UI에서는 미노출 (🔧 일부 구현 참고)

**게임 엔진**: Phaser 3 — 브라우저 내 커스텀 컴포넌트 (`components/phaser_game/`)

**적 유형 및 금융 개념 매핑** (`ai/quiz_generator.py` 기준)

| 세계 | patrol (순찰) | chaser (추적) | boss (보스) |
|------|-------------|-------------|-----------|
| `dinosaur` | 저축 | 용돈 관리 | 투자 |
| `space` | 주식이란? | 주식 투자 | 주식 시장 |
| `magic` | 예산 | 소비 습관 | 복리 |
| `ocean` | 보험 | 부채 관리 | 세금 |

**게임 이벤트 처리** (`_handle_game_event` in `app.py`)

| 이벤트 | 처리 내용 |
|--------|---------|
| `QUIZ_RESULT` | 정답/오답 쏠코인 지급, 히스토리 기록, 뱃지 체크 |
| `STAGE2_WIN` | 스테이지 2 클리어 기록 |
| `COIN_COLLECTED` | 맵 내 코인 습득 처리 |
| `WORLD_CLEAR` | 세계 클리어 기록 + `progress.json` 저장 |
| `GAME_OVER` | 게임 오버 화면 전환 |
| `NEWS_REQUEST` | 뉴스 페이지로 이동 |

---

### 3.3 AI 퀴즈 생성

✅ **구현 완료** (`ai/quiz_generator.py`)

- **모델**: GPT-4o-mini
- **입력**: 세계, 난이도, 나이 그룹, 캐릭터명, 적 유형, RAG 컨텍스트
- **출력**: 3지선다 JSON (question, choices, concept_card)
- **RAG 보강**: `RAGEngine`이 세계·개념 기반 관련 문서 검색 후 퀴즈 프롬프트에 주입
- **Fallback**: API 키 없음 또는 API 실패 시 `missions.json` 정적 문제 제공
- **절대 금지 규칙**: 숫자 계산 문제 생성 금지, 연령별 언어 수준 강제 제어

**나이별 언어 지침**

| age_group | 지침 |
|-----------|------|
| `young` | 초등 1~2학년 수준, 금융 전문 용어 사용 금지, 5단어 이내 선택지 |
| `middle` | 초등 고학년, 일반 금융 용어 가능, 계산 문제 금지 |
| `senior` | 개념 적용·비교 문제 가능, 계산 문제 금지 |

---

### 3.4 난이도 적응형 추천

✅ **구현 완료** (`ai/recommender.py`)

- `_answer_history` (session_state)에 누적된 답변 기록으로 정확도 계산
- 정확도 < 50% → `easy` / ≤ 80% → `medium` / > 80% → `hard`
- 취약 구역(`weak_zone_ids`) 우선 재추천
- 완료 구역 제외 후 스코어링 기반 최적 다음 구역 선택

---

### 3.5 RAG 기반 금융 개념 검색

✅ **구현 완료** (`ai/rag_engine.py`)

- **1차**: OpenAI `text-embedding-3-small` 임베딩 코사인 유사도 검색
- **2차 Fallback**: TF-IDF (char_wb, ngram 2~4) 코사인 유사도
- 모듈 레벨 임베딩 캐시(`_EMBED_CACHE`) — 프로세스 재시작 전까지 유지
- `ZONE_TO_DOC_IDS`로 구역별 관련 문서 직접 매핑
- 나이 그룹별 설명 버전 제공 (`age_young` / `age_middle` / `age_senior`)

---

### 3.6 뉴스 시스템

✅ **구현 완료** (`ai/news_crawler.py`)

**뉴스 수집 파이프라인**

```
RSS 크롤링 (매경·한경)
  └─ KoBERT 아동 적절성 필터
      └─ GPT-4o-mini 나이별 요약
          └─ 뉴스 페이지 표시
              └─ (senior) 기사별 AI 퀴즈 생성
```

**KoBERT 아동 적절성 필터**
- 모델: `maninglearchine/kobert-article-classifier` (HuggingFace)
- 레이블 `"적절"` → 통과 / 그 외 → 필터링
- 싱글톤 패턴으로 최초 1회 로드
- 로드 실패 시 모든 기사 통과 (Fallback)

**나이별 뉴스 기능**
- `young` / `middle`: GPT-4o-mini 어린이용 요약
- `senior`: 기사별 GPT-4o-mini 퀴즈 추가 생성 (`generate_news_quiz`)

**show_donyo 모드**: 뉴스 페이지 내 `music/shinhan.mp4` 재생 기능

**백그라운드 프리로드** (`kick_preloads`)
- Python `threading.Thread`로 뉴스 + 퀴즈 비동기 사전 로드
- 페이지 전환 시 로딩 대기 시간 최소화

---

### 3.7 뱃지 시스템

✅ **구현 완료** (`game/badge_engine.py`)

| 뱃지 ID | 이름 | 달성 조건 |
|--------|------|---------|
| `first_step` | 첫 발걸음 | 미션 1개 완료 |
| `saver` | 절약왕 | 저축 관련 미션 3개 완료 |
| `investor` | 투자 초보 | 투자 관련 미션 3개 완료 |
| `budget_master` | 예산 마스터 | 예산 관련 미션 3개 완료 |
| `interest_wizard` | 이자 마법사 | 이자 관련 미션 3개 완료 |
| `accuracy_star` | 정확도 스타 | 누적 정답률 80% 이상 |
| `explorer` | 세계 탐험가 | 2개 이상 세계에서 미션 완료 |
| `coin_master` | 코인 마스터 | 쏠코인 200개 이상 보유 |

**미션 분류 기준** (mission id prefix 매핑)
- `dino_` → saving 구역
- `space_` → invest 구역
- `magic_` → budget 구역
- `ocean_` → interest 구역

---

### 3.8 캐릭터 성장 시스템

✅ **구현 완료**

**레벨 시스템**
- 레벨 = (총 미션 완료 수 // 3) + 1
- 레벨당 3개 미션 완료로 레벨업
- 전체 진행도 = min(총 미션 수 / 12, 100%)

**캐릭터 진화 (쏠코인 기준)**

| 등급 | 조건 | 쏠쏠이 | 몰리 | 쏠리 |
|------|------|:------:|:----:|:----:|
| 새싹 탐험가 | coins < 50 | ⭐ | 🌸 | 🌊 |
| 금융 전사 | coins ≥ 50 | 🌟 | 🌺 | 🌈 |
| 주식 마스터 | coins ≥ 100 | 💫 | 💎 | ⚡ |

---

### 3.9 보호자 리포트

✅ **구현 완료** (`pages/parent_report.py`)

3개 탭으로 구성:

**탭 1: 오늘의 학습**
- 캐릭터 진화 단계 애니메이션 카드
- 쏠코인 / 완료 미션 수 / 정답률 3종 통계 카드
- 현재 세계별 금융 팁 3개 표시
- 완료 미션에서 추출한 금융 개념 카드 목록
- 취약 개념 재학습 권고 (개념별 정답률 60% 미만)
- Plotly 레이더 차트: 개념별 이해도 시각화

**탭 2: 뱃지 & 성취**
- 처치한 적 카드 (스테이지 1·2 클리어 시 이미지 언락)
- 획득 뱃지 갤러리 (4열 그리드)
- 미획득 뱃지 진행률 프로그레스 바

**탭 3: 금융상품 안내**

*자산 증여 상담 챗봇 (부모 전용)*
- LangChain + FAISS + PyPDF로 2개 PDF 문서 벡터화
  - `증여법관련.pdf`, `상속세 및 증여세법 시행령.pdf`
- 답변 흐름: PDF RAG → 출처 페이지 명시 → RAG 불충분 시 GPT-4o-mini Fallback
- 빠른 질문 버튼 3개 제공 (공제 한도, 증여 꿀팁 등)
- PDF 미존재 또는 langchain 미설치 시 GPT 단독 모드 자동 전환

*AI 맞춤 리포트*
- GPT-4o-mini가 배운 개념 목록 기반 200자 이내 부모 코멘트 생성
- API 실패 시 기본 템플릿 텍스트 Fallback

*추천 금융 상품*
- 우리아이통장 (어린이 전용 입출금)
- 우리아이 펀드 만들기 (비대면 미성년 전용 펀드)
- 면책 고지문 포함

---

### 3.10 생활 금융 도구 (상단 내비게이션)

✅ **구현 완료**

| 기능명 | 라우트 | 내용 |
|-------|--------|------|
| **오늘의 금융 단어** | `word` | 10개 단어를 날짜 MD5 해시로 1일 1단어 로테이션, 정의·팁 제공 |
| **용돈 기입장** | `allowance` | 수입/지출 기록, 잔액 자동 계산, 최근 20건 조회, session_state 저장 |
| **저축 목표** | `savings` | 목표 금액·이름 설정, 돼지 이모지 단계별 진행률, 목표 달성 시 풍선 효과 |
| **금융 상품** | `products` | 신한 5개 상품 카드 (주니어통장, 아이행복적금, 주니어적금, 어린이펀드, 청년처음적금) |
| **엄마 조르기** | `joreogi` | 학습 결과 + 신한 상품 3개 링크 포함 이메일 발송 (Gmail SMTP) |

**신한 금융 상품 5종** (`page_products`)

| 상품명 | 유형 | 대상 | 난이도 |
|-------|------|------|:------:|
| 신한 MY 주니어통장 | 통장 | 만 18세 이하 누구나 | ●○○ |
| 신한 아이행복 적금 | 적금 | 만 18세 이하 어린이 | ●○○ |
| 신한 MY 주니어 적금 | 적금 | 만 18세 이하 | ●●○ |
| 신한엄마사랑 어린이 펀드 | 펀드 | 부모 명의 투자 | ●●● |
| 청년 처음적금 (예비 청년용) | 미래 준비 | 중학생 이상~만 34세 | ●●○ |

---

### 3.11 엄마 조르기 / 부모 알림

✅ **구현 완료**

**이메일 발송** (`_render_naver_mail_btn`)
- Gmail SMTP (`smtp.gmail.com:465`, SSL)
- 환경 변수: `NAVER_MAIL_USER`, `NAVER_MAIL_PASS`, `MOM_EMAIL`
- 발송 내용: 캐릭터명, 탐험 세계, 퀴즈 완료 수, 성장 등급, 신한 상품 3개 링크
- HTML 이메일 + 텍스트 Fallback 동시 첨부

**SMS 발송** (MCP 서버, `mcp_servers/ncp_sms_server.py`)
- Aligo SMS API 연동
- 환경 변수: `ALIGO_API_KEY`, `ALIGO_USER_ID`, `ALIGO_SENDER`
- MCP stdio 서버로 구현 (`send_sms` 툴 제공)

🔧 **일부 구현** — 결과 페이지의 알림 버튼은 이메일 발송 방식으로 동작. Aligo MCP 서버는 별도 실행이 필요하며, 앱 내 SMS 직접 호출 연결은 미완성.

---

### 3.12 게임 상태 관리

✅ **구현 완료** (`game/state.py`)

- `GameState`: Streamlit session_state 래퍼 클래스
- 기본값: `coins=50`, `level=1`, `age_group="all"`, `world=None`
- `coin_log`: 코인 획득 히스토리 추적 (`add_coins(amount, label)`)
- `recalculate_level()`: 완료 미션 수 기반 레벨 자동 계산
- `get_progress_pct()`: 전체 12 미션 대비 진행률

**로컬 영속성** (`progress.json`)
- 저장 대상: `world_clear_*`, `stage2_clear` 미션 ID만 저장
- 새로고침 시 URL sid 기반 세션 복원 시도 (`game/persistence.py`)

---

### 3.13 BGM / 오디오

✅ **구현 완료** (`_inject_bgm`)

- `/app/static/bgm.wav` 배경음악 전 페이지 자동 재생 (`<audio autoplay loop>`)
- `music/shinhan.mp4`: 뉴스 페이지 `show_donyo` 모드에서 재생

---

## 4. 기술 스택

| 분류 | 기술 | 용도 |
|------|------|------|
| **웹 프레임워크** | Streamlit ≥ 1.35 | 전체 UI 및 앱 서버 |
| **게임 엔진** | Phaser 3 | 브라우저 내 RPG 게임 컴포넌트 |
| **LLM** | OpenAI GPT-4o-mini | 퀴즈 생성, 뉴스 요약, 부모 리포트 생성 |
| **임베딩** | OpenAI text-embedding-3-small | RAG 벡터 유사도 검색 |
| **아동 필터** | KoBERT (`maninglearchine/kobert-article-classifier`) | 뉴스 아동 적절성 분류 |
| **문서 RAG** | LangChain + FAISS + PyPDF | 증여세 PDF Q&A 챗봇 |
| **검색 Fallback** | TF-IDF (scikit-learn, char_wb n-gram) | 임베딩 없을 때 RAG 대체 |
| **차트** | Plotly | 개념 이해도 레이더 차트 |
| **이메일** | Gmail SMTP (smtplib) | 엄마 조르기 HTML 이메일 발송 |
| **SMS** | Aligo API (MCP stdio 서버) | 부모 SMS 발송 |
| **비동기** | Python `threading.Thread` | 뉴스·퀴즈 백그라운드 프리로드 |
| **데이터** | JSON (`worlds.json`, `missions.json`, `finance_concepts.json`) | 세계·미션·개념 정의 |
| **환경변수** | python-dotenv | API 키 보안 관리 |

---

## 5. 데이터 구조

### 5.1 게임 상태 (session_state 주요 키)

| 키 | 타입 | 설명 |
|----|------|------|
| `page` | str | 현재 페이지 라우트 |
| `world` | str\|None | 선택된 세계 ID |
| `character_name` | str | 선택된 캐릭터명 |
| `age_group` | str | 나이 그룹 (`young`/`middle`/`senior`) |
| `coins` | int | 쏠코인 (초기값 50) |
| `level` | int | 현재 레벨 |
| `completed_missions` | list[str] | 완료 미션 ID 목록 |
| `badges` | list[str] | 획득 뱃지 ID 목록 |
| `coin_log` | list[dict] | 코인 획득 히스토리 |
| `_answer_history` | list[dict] | 퀴즈 답변 기록 (zone_id, concept, correct) |
| `allowance_records` | list[dict] | 용돈 기입장 기록 |
| `savings_goal` | int | 저축 목표 금액 |
| `savings_saved` | int | 현재 저금 금액 |
| `gift_chat_history` | list[dict] | 증여 상담 챗봇 대화 이력 |

### 5.2 AI 퀴즈 JSON 스키마

```json
{
  "question": "질문 (세계 배경 포함, 숫자 계산 없음)",
  "choices": [
    {"id": "a", "text": "선택지", "correct": true,  "feedback": "피드백", "coins": 15},
    {"id": "b", "text": "선택지", "correct": false, "feedback": "피드백", "coins": -5},
    {"id": "c", "text": "선택지", "correct": false, "feedback": "피드백", "coins": -5}
  ],
  "concept_card": {
    "title": "오늘의 금융 개념: {concept}",
    "body": "핵심 한 줄 설명",
    "emoji": "💰"
  }
}
```

---

## 6. 환경 변수 (.env)

| 변수명 | 필수 | 용도 |
|--------|:----:|------|
| `OPENAI_API_KEY` | ✅ | GPT-4o-mini, text-embedding-3-small |
| `HF_TOKEN` | ✅ | HuggingFace KoBERT 모델 로드 |
| `NAVER_MAIL_USER` | 선택 | Gmail 발신 계정 (엄마 조르기) |
| `NAVER_MAIL_PASS` | 선택 | Gmail 앱 비밀번호 |
| `MOM_EMAIL` | 선택 | 보호자 수신 이메일 |
| `ALIGO_API_KEY` | 선택 | Aligo SMS API 키 |
| `ALIGO_USER_ID` | 선택 | Aligo 로그인 ID |
| `ALIGO_SENDER` | 선택 | Aligo 등록 발신번호 |

---

## 7. 페이지 라우팅

| 라우트 | 함수 | 설명 |
|--------|------|------|
| `onboarding` | `page_onboarding` | 4단계 온보딩 |
| `map` | `page_map` | 세계 지도 + 구역 선택 |
| `mission` | `page_mission` | 미션 실행 (Phaser 3 게임) |
| `report` | `page_report` | 미션 결과 + 보호자 리포트 |
| `news` | `page_news` | 금융 뉴스 목록 |
| `result` | `page_result` | 게임 최종 결과 화면 |
| `word` | `page_word_of_day` | 오늘의 금융 단어 |
| `allowance` | `page_allowance` | 용돈 기입장 |
| `savings` | `page_savings` | 저축 목표 트래커 |
| `products` | `page_products` | 신한 금융 상품 안내 |
| `joreogi` | `page_joreogi` | 엄마 조르기 |

---

## 8. 구현 상태 요약

### ✅ 구현 완료

- 4단계 온보딩 (캐릭터 · 나이 · 세계 · 인트로)
- Phaser 3 기반 RPG 게임 (적 격퇴 + 퀴즈)
- GPT-4o-mini AI 퀴즈 생성 (`missions.json` Fallback 포함)
- KoBERT 뉴스 아동 적절성 필터링
- 뉴스 GPT 요약 (나이별 언어 수준)
- senior 뉴스 AI 퀴즈 생성
- 8종 뱃지 시스템 + 미션 분류 자동화
- 3티어 캐릭터 진화 (캐릭터별 개별 이모지)
- 적응형 난이도 추천 (정확도 기반)
- RAG 금융 개념 검색 (TF-IDF + 임베딩 병렬)
- 보호자 리포트 3탭 (학습 · 뱃지 · 상품)
- 증여세 PDF RAG 챗봇 (LangChain + FAISS)
- 오늘의 금융 단어 (10종, 날짜 해시 로테이션)
- 용돈 기입장 (수입/지출 기록 + 잔액 계산)
- 저축 목표 트래커 (진행률 시각화)
- 신한 금융 상품 5종 안내 (난이도 · 비유 설명 포함)
- 엄마 조르기 이메일 발송 (HTML + 텍스트 형식)
- BGM 자동 재생 (`bgm.wav`)
- `progress.json` 로컬 영속성 (세계·스테이지 클리어)
- Aligo SMS MCP 서버 구현 (`send_sms` 툴)
- 백그라운드 뉴스·퀴즈 프리로드 (threading)
- Plotly 개념 이해도 레이더 차트

### 🔧 일부 구현

- **dinosaur 세계**: `worlds.json`에 정의 완료, 온보딩 UI 미노출
- **SMS 발송**: Aligo MCP 서버 구현 완료, 앱 내 호출 연결 미완성 (결과 페이지는 이메일 방식 사용)
- **URL 세션 복원**: `game/persistence.py` 구현, 동작 조건 제한적
- **신한 상품 링크**: 실제 URL 연결되나 실시간 금리·조건 반영 불가 (정적 데이터)

### 🔮 향후 확장 가능

- dinosaur 세계 온보딩 노출 및 전체 활성화
- 실시간 신한 상품 API 연동 (금리·조건 자동 업데이트)
- 다중 세계 순차 클리어 구조 (현재 1세계 선택 후 플레이)
- 보호자 대시보드 별도 분리 (현재 report 탭 내 혼재)
- 용돈 기입장 서버 사이드 영속성 (현재 session_state 한정)
- 저축 목표 다중 설정 (현재 1개 목표만)
- AI 기반 학습 경로 추천 강화 (현재 규칙 기반)

---

## 9. 서비스 플로우

```
시작
 └─ 온보딩 (캐릭터 → 나이 → 세계 → 인트로)
     └─ 맵 화면 (세계 지도 + 구역 선택)
         └─ 미션 화면 (Phaser 3 게임)
             ├─ 퀴즈 (GPT-4o-mini 생성 or missions.json fallback)
             │    ├─ 정답: 쏠코인 +15, 뱃지 체크
             │    └─ 오답: 쏠코인 -5
             ├─ 스테이지 1 클리어 → world_clear_* 저장
             └─ 스테이지 2 클리어 → stage2_clear 저장
                 └─ 결과 화면
                     ├─ 학습 성과 요약
                     ├─ 엄마 조르기 이메일 발송
                     └─ 보호자 리포트 (학습 · 뱃지 · 상품)

상단 내비게이션 (항상 접근 가능)
 ├─ 📖 단어장 → 오늘의 금융 단어
 ├─ 💰 용돈기입장 → 수입/지출 기록
 ├─ 🐷 저축목표 → 목표 설정 · 저금
 ├─ 🏦 금융상품 → 신한 5개 상품 카드
 └─ 🎮 게임 → 맵으로 이동
```

---

*본 문서는 실제 구현된 소스코드(`app.py`, `game/`, `ai/`, `pages/`, `data/`, `mcp_servers/`)를 기반으로 역기획 방식으로 작성되었습니다. 코드에 없는 기능은 포함하지 않았습니다.*
