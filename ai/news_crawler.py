"""
Korean stock news crawler + child-friendly summarizer (OpenAI).
KoBERT 기반 어린이 적합성 필터 적용 (maninglearchine/kobert-article-classifier)
네이버 경제 뉴스 8개 섹션 크롤링 방식
"""

import re
import time
import random

import requests
from bs4 import BeautifulSoup
import openai

# 네이버 경제 뉴스 섹션 sid2 → 섹션명
NAVER_SECTIONS = {
    259: "금융",
    258: "증권",
    261: "산업/재계",
    771: "중기/벤처",
    260: "부동산",
    262: "글로벌경제",
    310: "생활경제",
    263: "경제일반",
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Referer": "https://news.naver.com/",
    "Accept-Language": "ko-KR,ko;q=0.9",
}

# KoBERT 분류기 싱글톤 (최초 호출 시 1회만 로드)
_kobert_classifier = None
KOBERT_MODEL_ID = "maninglearchine/kobert-article-classifier"
KOBERT_MAX_LEN  = 64


def _get_kobert():
    global _kobert_classifier
    if _kobert_classifier is None:
        try:
            from transformers import pipeline as hf_pipeline
            _kobert_classifier = hf_pipeline(
                "text-classification",
                model=KOBERT_MODEL_ID,
                device=-1,          # CPU
                truncation=True,
                max_length=KOBERT_MAX_LEN,
            )
        except Exception as e:
            print(f"[KoBERT] 모델 로드 실패, 필터 비활성화: {e}")
            _kobert_classifier = None
    return _kobert_classifier


def _is_child_appropriate(title: str, description: str) -> bool:
    """KoBERT로 기사가 어린이 교육 목적에 적합한지 판별한다.
    모델 로드 실패 시 True를 반환해 기존 흐름을 유지한다.
    """
    clf = _get_kobert()
    if clf is None:
        return True  # fallback: 필터 없이 통과
    text = f"{title} {description}"[:200]
    result = clf(text)[0]
    return result["label"] == "적절"


def _fetch_section_links(sid2: int, per_section: int) -> list[dict]:
    """네이버 섹션 목록 페이지에서 기사 링크를 수집한다."""
    url = f"https://news.naver.com/main/list.naver?mode=LS2D&mid=shm&sid1=101&sid2={sid2}"
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(r.text, "html.parser")
    except Exception:
        return []

    articles, seen = [], set()
    for a in soup.select("a[href*='mnews/article/']"):
        href = a.get("href", "")
        if "comment" in href or href in seen:
            continue
        title = a.get_text(strip=True)
        if not title or len(title) < 8:
            continue
        # 동영상 뉴스 항목 제외 (제목이 재생시간 형태)
        if re.search(r"동영상뉴스|재생시간", title):
            continue
        seen.add(href)
        link = href if href.startswith("http") else "https://n.news.naver.com" + href
        articles.append({"title": title, "description": "", "link": link})
        if len(articles) >= per_section:
            break
    return articles


def _fetch_body(article: dict) -> dict:
    """기사 본문 첫 400자를 description에 채운다 (실패 시 제목으로 대체)."""
    try:
        time.sleep(random.uniform(0.05, 0.15))
        r = requests.get(article["link"], headers=HEADERS, timeout=10)
        soup = BeautifulSoup(r.text, "html.parser")
        el = soup.select_one("#dic_area")
        article["description"] = el.get_text(" ", strip=True)[:400] if el else article["title"]
    except Exception:
        article["description"] = article["title"]
    return article


def fetch_stock_news(n: int = 5) -> list[dict]:
    """네이버 경제 섹션 크롤링 → KoBERT 필터 → 상위 n건 반환."""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    # 섹션당 수집량: KoBERT 필터 손실을 고려해 넉넉하게
    per_section = max(2, (n * 3 + len(NAVER_SECTIONS) - 1) // len(NAVER_SECTIONS))

    # 1단계: 섹션별 기사 링크 병렬 수집
    raw: list[dict] = []
    with ThreadPoolExecutor(max_workers=len(NAVER_SECTIONS)) as pool:
        futs = {pool.submit(_fetch_section_links, sid2, per_section): sid2
                for sid2 in NAVER_SECTIONS}
        for fut in as_completed(futs):
            raw.extend(fut.result())

    # 중복 링크 제거
    seen_links: set[str] = set()
    deduped: list[dict] = []
    for a in raw:
        if a["link"] not in seen_links:
            seen_links.add(a["link"])
            deduped.append(a)

    # 2단계: 기사 본문 병렬 수집
    with ThreadPoolExecutor(max_workers=8) as pool:
        futs_body = [pool.submit(_fetch_body, a) for a in deduped]
        for fut in as_completed(futs_body):
            fut.result()

    # 3단계: KoBERT 적합성 필터
    filtered = [a for a in deduped if _is_child_appropriate(a["title"], a["description"])]

    if len(filtered) < n:
        remaining = [a for a in deduped if a not in filtered]
        filtered.extend(remaining[: n - len(filtered)])

    return filtered[:n]


def summarize_news_for_kids(
    articles: list[dict],
    client: openai.OpenAI,
    age_group: str = "elementary",
    character_name: str = "쏠쏠이",
) -> list[dict]:
    if not articles:
        return []

    age_desc = {
        "young":      "초등학교 저학년(7~9세)",
        "middle":     "초등학교 고학년(10~12세)",
        "senior":     "중학생(13세 이상)",
        "all":        "어린이",
        "elementary": "초등학교 저학년",
    }.get(age_group, "어린이")
    article_text = "\n".join(
        f"[{i+1}] 제목: {a['title']}\n내용: {a['description']}"
        for i, a in enumerate(articles)
    )

    prompt = f"""너는 어린이 금융 교육 캐릭터 {character_name}야.
아래 한국 금융·경제 뉴스 {len(articles)}개를 {age_desc} 어린이도 이해할 수 있게 쉽고 재미있게 설명해줘.

각 뉴스마다 JSON 배열 원소 하나를 만들어:
{{
  "emoji": "뉴스 내용에 맞는 이모지 1개",
  "title": "어린이용 제목 (15자 이내)",
  "summary": "{character_name}가 설명하는 쉬운 2-3문장 요약",
  "lesson": "이 뉴스에서 배울 수 있는 금융 교훈 1문장"
}}

뉴스 목록:
{article_text}

반드시 JSON 배열만 출력해. 다른 텍스트 없이."""

    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
        max_tokens=1200,
        response_format={"type": "json_object"},
    )

    import json
    raw = resp.choices[0].message.content or "{}"
    parsed = json.loads(raw)

    # The model may wrap the array in a key — unwrap it
    if isinstance(parsed, dict):
        for v in parsed.values():
            if isinstance(v, list):
                parsed = v
                break
        else:
            parsed = []

    result = []
    for i, item in enumerate(parsed):
        if not isinstance(item, dict):
            continue
        result.append({
            "emoji":   item.get("emoji", "📰"),
            "title":   item.get("title", articles[i]["title"][:20] if i < len(articles) else "뉴스"),
            "summary": item.get("summary", ""),
            "lesson":  item.get("lesson", ""),
            "link":    articles[i]["link"] if i < len(articles) else "",
        })
    return result


def get_kids_news(
    n: int = 5,
    age_group: str = "elementary",
    character_name: str = "쏠쏠이",
) -> list[dict]:
    from dotenv import load_dotenv
    import os
    load_dotenv()
    client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    articles = fetch_stock_news(n)
    if not articles:
        return []
    return summarize_news_for_kids(articles, client, age_group, character_name)


# ── Step 3 — 뉴스 기반 퀴즈 생성 (13세 이상 전용) ───────────────────────────

def generate_news_quiz(
    item: dict,
    age_group: str = "senior",
    api_key: str | None = None,
) -> dict | None:
    """어린이용 뉴스 아이템을 기반으로 서비스 포맷 3지선다 퀴즈를 생성한다.

    item 은 summarize_news_for_kids() 가 반환한 dict:
      {emoji, title, summary, lesson, link}
    반환 포맷은 QuizGenerator._openai_quiz() 와 동일:
      {question, choices[{id,text,correct,feedback,coins}], concept_card}
    """
    import os
    import json
    from dotenv import load_dotenv
    load_dotenv()

    key = api_key or os.getenv("OPENAI_API_KEY")
    if not key:
        return None

    age_map = {
        "young":  "초등학교 저학년(7~9세)",
        "middle": "초등학교 고학년(10~12세)",
        "senior": "중학생(13세 이상)",
        "all":    "어린이",
    }
    age_desc = age_map.get(age_group, "중학생(13세 이상)")

    content = "\n".join(filter(None, [
        f"제목: {item.get('title', '')}",
        f"요약: {item.get('summary', '')}",
        f"교훈: {item.get('lesson', '')}",
    ]))

    prompt = f"""다음 금융 뉴스를 바탕으로 {age_desc}을 위한 3지선다 퀴즈를 만드세요.

{content}

반드시 아래 JSON 형식으로만 출력하세요:
{{
  "question": "퀴즈 문제 (뉴스 내용 기반, 1~2문장)",
  "choices": [
    {{"id":"a","text":"선택지","correct":true,"feedback":"왜 맞는지 한 문장","coins":15}},
    {{"id":"b","text":"선택지","correct":false,"feedback":"왜 틀렸는지","coins":-5}},
    {{"id":"c","text":"선택지","correct":false,"feedback":"왜 틀렸는지","coins":-5}}
  ],
  "concept_card": {{
    "title": "오늘의 금융 개념",
    "body": "이 뉴스에서 배울 수 있는 핵심 금융 교훈 한 문장",
    "emoji": "관련 이모지"
  }}
}}

choices 중 정확히 하나만 correct: true. JSON만 출력."""

    try:
        client = openai.OpenAI(api_key=key)
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=600,
            response_format={"type": "json_object"},
        )
        data = json.loads(resp.choices[0].message.content)
        assert "question" in data
        assert "choices" in data and len(data["choices"]) >= 2
        assert any(c.get("correct") for c in data["choices"])
        return data
    except Exception:
        return None
