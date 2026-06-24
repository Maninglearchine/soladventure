"""
Korean stock news crawler + child-friendly summarizer (OpenAI).
"""

import xml.etree.ElementTree as ET
import html
import re

import requests
import openai

RSS_FEEDS = [
    "https://www.mk.co.kr/rss/40300001/",
    "https://www.hankyung.com/feed/economy",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}

# Step 1 — 금융 키워드 필터 (title + description 검사)
FINANCE_KEYWORDS = [
    "돈", "용돈", "소비", "저축", "통장", "이자", "가격", "물가",
    "환전", "투자", "주식", "금리", "환율", "경제", "은행", "세금",
    "예금", "적금", "펀드", "채권", "금융", "대출", "부채",
]


def _strip_tags(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _parse_rss(url: str, n: int) -> list[dict]:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=8)
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
    except Exception:
        return []

    matched, others = [], []
    for item in root.iter("item"):
        title = _strip_tags(item.findtext("title", ""))
        desc  = _strip_tags(item.findtext("description", ""))
        link  = (item.findtext("link") or "").strip()
        if not title:
            continue
        entry = {"title": title, "description": desc[:400], "link": link}
        if any(kw in title + " " + desc for kw in FINANCE_KEYWORDS):
            matched.append(entry)
        else:
            others.append(entry)
        if len(matched) + len(others) >= n * 4:
            break

    # 금융 키워드 기사 우선, 없으면 전체에서 반환
    return (matched if matched else others)[:n]


def fetch_stock_news(n: int = 5) -> list[dict]:
    from concurrent.futures import ThreadPoolExecutor, as_completed
    per_feed = max(1, (n + len(RSS_FEEDS) - 1) // len(RSS_FEEDS))
    articles = []
    with ThreadPoolExecutor(max_workers=len(RSS_FEEDS)) as pool:
        futures = [pool.submit(_parse_rss, url, per_feed) for url in RSS_FEEDS]
        for fut in as_completed(futures):
            articles.extend(fut.result())
    return articles[:n]


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
아래 한국 주식 뉴스 {len(articles)}개를 {age_desc} 어린이도 이해할 수 있게 쉽고 재미있게 설명해줘.

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
