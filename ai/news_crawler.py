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

    items = []
    for item in root.iter("item"):
        title = _strip_tags(item.findtext("title", ""))
        desc  = _strip_tags(item.findtext("description", ""))
        link  = (item.findtext("link") or "").strip()
        if title:
            items.append({"title": title, "description": desc[:400], "link": link})
        if len(items) >= n:
            break
    return items


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

    age_desc = "초등학교 저학년" if age_group == "elementary" else "초등학교 고학년"
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
