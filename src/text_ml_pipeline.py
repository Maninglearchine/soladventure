"""
크롤링 뉴스 텍스트 기반 머신러닝 파이프라인
실행: python src/text_ml_pipeline.py
"""
import sys, os, re, warnings, time, html as html_module
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
warnings.filterwarnings("ignore")

from pathlib import Path
import pandas as pd
import numpy as np

# ── 경로 ──────────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
EDA_DIR  = BASE_DIR / "outputs" / "eda"
ML_DIR   = BASE_DIR / "outputs" / "ml"
for d in [DATA_DIR, EDA_DIR, ML_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# ── matplotlib 한국어 설정 ─────────────────────────────────────────────────────
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm

# Windows 맑은 고딕 / Linux NanumGothic 순으로 탐색
_KO_FONT = None
for _fp in [
    "C:/Windows/Fonts/malgun.ttf",
    "C:/Windows/Fonts/NanumGothic.ttf",
    "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
]:
    if Path(_fp).exists():
        _KO_FONT = _fp
        fm.fontManager.addfont(_fp)
        _prop = fm.FontProperties(fname=_fp)
        matplotlib.rcParams["font.family"] = _prop.get_name()
        break

matplotlib.rcParams["axes.unicode_minus"] = False
import seaborn as sns

# ── 경제 키워드 사전 ──────────────────────────────────────────────────────────
ECONOMIC_KEYWORDS = [
    "환율","금리","물가","예금","적금","저축","통장","이자","투자","펀드",
    "주식","증시","코스피","코스닥","소비","가격","대출","원화","달러",
    "위험","변동성","기준금리","유동성","통화정책","인플레이션","디플레이션",
    "경기침체","자산배분","환헤지","용돈","저금","돈","은행","절약",
    "지출","수입","세금","파생상품","레버리지","채권","복리","양적완화",
    "헤지","선물","옵션","스왑","신용","담보","시장","할인","목표",
]

SAVING_WORDS  = {"저축","적금","예금","저금","통장","저금통","목표"}
INVEST_WORDS  = {"투자","펀드","주식","증시","코스피","코스닥","채권","선물","옵션"}
RISK_WORDS    = {"위험","변동성","환헤지","헤지","경기침체","리스크","환리스크","레버리지"}


# ══════════════════════════════════════════════════════════════════════════════
# 1. 뉴스 데이터 로드
# ══════════════════════════════════════════════════════════════════════════════
def load_news_data() -> pd.DataFrame:
    csv_path = DATA_DIR / "news_articles.csv"
    if csv_path.exists():
        print(f"[로드] 기존 CSV: {csv_path}")
        df = pd.read_csv(csv_path, encoding="utf-8-sig")
    else:
        print("[크롤링] news_articles.csv 없음 → 실시간 크롤링...")
        from ai.news_crawler import _fetch_section_links, _fetch_body, NAVER_SECTIONS
        from concurrent.futures import ThreadPoolExecutor, as_completed
        import datetime

        raw = []
        with ThreadPoolExecutor(max_workers=8) as pool:
            futs = {
                pool.submit(_fetch_section_links, sid2, 15): (sid2, name)
                for sid2, name in NAVER_SECTIONS.items()
            }
            for fut in as_completed(futs):
                sid2, name = futs[fut]
                arts = fut.result()
                for a in arts:
                    a["source"] = name
                raw.extend(arts)
                print(f"  [{name}] {len(arts)}건")

        seen, deduped = set(), []
        for a in raw:
            if a["link"] not in seen:
                seen.add(a["link"]); deduped.append(a)

        print(f"[본문 수집] {len(deduped)}건...")
        with ThreadPoolExecutor(max_workers=16) as pool:
            futs2 = [pool.submit(_fetch_body, a) for a in deduped]
            for f in as_completed(futs2):
                f.result()

        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        df = pd.DataFrame([{
            "title":       a.get("title",""),
            "description": a.get("description",""),
            "link":        a.get("link",""),
            "source":      a.get("source",""),
            "collected_at": ts,
        } for a in deduped])
        df.to_csv(csv_path, index=False, encoding="utf-8-sig")
        print(f"[저장] {len(df)}건 → {csv_path}")

    print(f"[로드 완료] {len(df)}건")
    return df


# ══════════════════════════════════════════════════════════════════════════════
# 2. 텍스트 전처리
# ══════════════════════════════════════════════════════════════════════════════
def preprocess_text(text: str) -> str:
    if not isinstance(text, str) or not text.strip():
        return ""
    t = re.sub(r"<[^>]+>", " ", text)              # HTML 태그 제거
    t = html_module.unescape(t)                     # HTML 엔티티 복원
    t = re.sub(r"\S+@\S+", " ", t)                 # 이메일 제거
    t = re.sub(r"[가-힣]{2,4}\s*(기자|특파원|선임기자|논설위원)", " ", t)  # 기자명
    t = re.sub(r"(ⓒ|©|무단\s*전재|재배포\s*금지|저작권)", " ", t)        # 저작권
    t = re.sub(r"(구독|클릭|바로가기|더보기|관련기사|AD|광고)", " ", t)    # 광고
    t = re.sub(r"[^\w\s가-힣]", " ", t)            # 특수문자 제거
    t = re.sub(r"\b\d+\b", " ", t)                 # 단독 숫자 제거
    t = re.sub(r"\s+", " ", t).strip()             # 공백 정리
    return t


def preprocess_df(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["title"]       = df["title"].fillna("")
    df["description"] = df["description"].fillna("")
    df["text_raw"]    = df["title"] + " " + df["description"]
    df["text"]        = df["text_raw"].apply(preprocess_text)

    before = len(df)
    df = df[df["text"].str.len() >= 20].copy()     # 너무 짧은 텍스트 제거
    df = df.drop_duplicates(subset="text").reset_index(drop=True)
    print(f"[전처리] {before}건 → {len(df)}건 (짧은 텍스트·중복 제거)")
    return df


# ══════════════════════════════════════════════════════════════════════════════
# 3. 경제 키워드 추출
# ══════════════════════════════════════════════════════════════════════════════
def extract_economic_keywords(text: str) -> list:
    return [kw for kw in ECONOMIC_KEYWORDS if kw in text]


# ══════════════════════════════════════════════════════════════════════════════
# 4. 라벨 데이터 로드
# ══════════════════════════════════════════════════════════════════════════════
def build_labeled_dataset() -> pd.DataFrame:
    label_path = DATA_DIR / "child_friendly_labels.csv"
    df = pd.read_csv(label_path, encoding="utf-8-sig")
    print(f"[라벨] {len(df)}건  label=1: {df['label'].sum()}건  label=0: {(df['label']==0).sum()}건")
    return df


# ══════════════════════════════════════════════════════════════════════════════
# 5. ML 학습 데이터 생성 (키워드 수준 + 기사 수준)
# ══════════════════════════════════════════════════════════════════════════════
def build_ml_dataset(news_df: pd.DataFrame, label_df: pd.DataFrame):
    label_map = dict(zip(label_df["keyword"], label_df["label"]))

    # ── 키워드 수준 학습셋 ────────────────────────────────────────────────────
    # 기사에서 라벨된 키워드가 등장한 모든 (기사, 키워드) 쌍 생성
    kw_rows = []
    for _, row in news_df.iterrows():
        kws = extract_economic_keywords(row["text"])
        labeled = [(kw, label_map[kw]) for kw in kws if kw in label_map]
        for kw, lbl in labeled:
            kw_rows.append({
                "text":              row["text"],
                "keyword":           kw,
                "label":             lbl,
                "keyword_count":     len(kws),
                "text_length":       len(row["text"]),
                "keyword_length":    len(kw),
                "has_investment_word": int(any(w in row["text"] for w in INVEST_WORDS)),
                "has_saving_word":   int(any(w in row["text"] for w in SAVING_WORDS)),
                "has_risk_word":     int(any(w in row["text"] for w in RISK_WORDS)),
            })

    kw_ml = pd.DataFrame(kw_rows)

    # ── 기사 수준 라벨 (keyword label 비율) ──────────────────────────────────
    article_rows = []
    for _, row in news_df.iterrows():
        kws = extract_economic_keywords(row["text"])
        labeled = [label_map[kw] for kw in kws if kw in label_map]
        if not labeled:
            continue
        art_label = 1 if (sum(labeled) / len(labeled)) >= 0.5 else 0
        article_rows.append({
            "text":              row["text"],
            "source":            row.get("source",""),
            "matched_keywords":  ",".join([kw for kw in kws if kw in label_map]),
            "label":             art_label,
            "keyword_count":     len(kws),
            "text_length":       len(row["text"]),
            "has_investment_word": int(any(w in row["text"] for w in INVEST_WORDS)),
            "has_saving_word":   int(any(w in row["text"] for w in SAVING_WORDS)),
            "has_risk_word":     int(any(w in row["text"] for w in RISK_WORDS)),
        })

    art_ml = pd.DataFrame(article_rows)

    # ── 라벨 키워드 자체도 학습 샘플로 추가 (데이터 확장) ────────────────────
    extra_rows = []
    for _, row in label_df.iterrows():
        extra_rows.append({
            "text":              row["keyword"],
            "keyword":           row["keyword"],
            "label":             row["label"],
            "keyword_count":     1,
            "text_length":       len(row["keyword"]),
            "keyword_length":    len(row["keyword"]),
            "has_investment_word": int(row["keyword"] in INVEST_WORDS),
            "has_saving_word":   int(row["keyword"] in SAVING_WORDS),
            "has_risk_word":     int(row["keyword"] in RISK_WORDS),
        })
    extra_df = pd.DataFrame(extra_rows)

    if len(kw_ml) > 0:
        kw_ml = pd.concat([kw_ml, extra_df], ignore_index=True).drop_duplicates(subset=["text","keyword"])
    else:
        kw_ml = extra_df

    print(f"[ML 데이터] 키워드 수준: {len(kw_ml)}건  기사 수준: {len(art_ml)}건")
    if len(kw_ml) < 20:
        print("  ⚠️  학습 데이터가 적습니다. 교차검증으로 대체합니다.")

    # 저장
    kw_ml.to_csv(ML_DIR / "keyword_ml_dataset.csv", index=False, encoding="utf-8-sig")
    if len(art_ml) > 0:
        art_ml.to_csv(ML_DIR / "article_ml_dataset.csv", index=False, encoding="utf-8-sig")

    return kw_ml, art_ml


# ══════════════════════════════════════════════════════════════════════════════
# 6. EDA
# ══════════════════════════════════════════════════════════════════════════════
def run_eda(news_df: pd.DataFrame, label_df: pd.DataFrame):
    print("\n[EDA] 그래프 생성 중...")

    # ── 경제 키워드 Top 20 countplot ─────────────────────────────────────────
    from collections import Counter
    all_kws = []
    for text in news_df["text"]:
        all_kws.extend(extract_economic_keywords(text))
    kw_counter = Counter(all_kws)

    top20 = pd.DataFrame(kw_counter.most_common(20), columns=["keyword","count"])
    fig, ax = plt.subplots(figsize=(12, 6))
    palette = ["#4CAF50" if k in {r["keyword"] for _, r in label_df[label_df["label"]==1].iterrows()} else "#F44336"
               for k in top20["keyword"]]
    sns.barplot(data=top20, x="count", y="keyword", palette=palette, ax=ax)
    ax.set_title("경제 키워드 Top 20 (초록=아이 친화, 빨강=비친화)", fontsize=14, fontweight="bold")
    ax.set_xlabel("출현 빈도")
    ax.set_ylabel("키워드")
    plt.tight_layout()
    fig.savefig(EDA_DIR / "top20_keywords.png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    print("  ✅ top20_keywords.png")

    # ── 라벨 분포 ─────────────────────────────────────────────────────────────
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))

    label_counts = label_df["label"].value_counts()
    colors = ["#4CAF50","#F44336"]
    axes[0].pie(label_counts, labels=["아이 친화(1)","비친화(0)"][::-1] if label_counts.index[0]==0 else ["아이 친화(1)","비친화(0)"],
                colors=colors, autopct="%1.1f%%", startangle=90, textprops={"fontsize":12})
    axes[0].set_title("라벨 키워드 분포", fontsize=13, fontweight="bold")

    sns.countplot(data=label_df, x="label", palette={0:"#F44336", 1:"#4CAF50"},
                  hue="label", legend=False, ax=axes[1])
    axes[1].set_title("라벨별 키워드 수", fontsize=13, fontweight="bold")
    axes[1].set_xlabel("label  (1=아이 친화  0=비친화)")
    axes[1].set_ylabel("키워드 수")
    axes[1].set_xticks([0,1])
    axes[1].set_xticklabels(["비친화(0)","아이 친화(1)"])
    plt.tight_layout()
    fig.savefig(EDA_DIR / "label_distribution.png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    print("  ✅ label_distribution.png")

    # ── 금융 주제별 분포 ──────────────────────────────────────────────────────
    topic_map = {
        "저축/예금":   SAVING_WORDS,
        "투자/주식":   INVEST_WORDS,
        "위험/리스크": RISK_WORDS,
        "기타":        set(ECONOMIC_KEYWORDS) - SAVING_WORDS - INVEST_WORDS - RISK_WORDS,
    }
    topic_counts = {}
    for text in news_df["text"]:
        for topic, words in topic_map.items():
            if any(w in text for w in words):
                topic_counts[topic] = topic_counts.get(topic, 0) + 1

    if topic_counts:
        fig, ax = plt.subplots(figsize=(8, 5))
        topic_df = pd.DataFrame(list(topic_counts.items()), columns=["topic","count"]).sort_values("count", ascending=False)
        sns.barplot(data=topic_df, x="count", y="topic",
                    palette=["#2196F3","#FF9800","#E91E63","#9C27B0"], ax=ax)
        ax.set_title("금융 주제별 기사 분포", fontsize=13, fontweight="bold")
        ax.set_xlabel("기사 수")
        ax.set_ylabel("주제")
        plt.tight_layout()
        fig.savefig(EDA_DIR / "topic_distribution.png", dpi=150, bbox_inches="tight")
        plt.close(fig)
        print("  ✅ topic_distribution.png")

    # ── 텍스트 길이 분포 ──────────────────────────────────────────────────────
    fig, ax = plt.subplots(figsize=(10, 5))
    news_df["text_length"] = news_df["text"].str.len()
    ax.hist(news_df["text_length"], bins=30, color="#1E88E5", edgecolor="white", alpha=0.85)
    ax.axvline(news_df["text_length"].median(), color="red", linestyle="--", linewidth=1.5, label=f"중앙값 {news_df['text_length'].median():.0f}자")
    ax.set_title("기사 텍스트 길이 분포", fontsize=13, fontweight="bold")
    ax.set_xlabel("텍스트 길이 (문자 수)")
    ax.set_ylabel("기사 수")
    ax.legend()
    plt.tight_layout()
    fig.savefig(EDA_DIR / "text_length_distribution.png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    print("  ✅ text_length_distribution.png")

    # ── WordCloud ─────────────────────────────────────────────────────────────
    try:
        from wordcloud import WordCloud
        all_text = " ".join(news_df["text"].tolist())
        wc_kwargs = dict(
            width=1200, height=600, background_color="white",
            max_words=100, colormap="RdYlGn",
            regexp=r"[가-힣]{2,}",
        )
        if _KO_FONT:
            wc_kwargs["font_path"] = _KO_FONT
        wc = WordCloud(**wc_kwargs).generate(all_text)
        fig, ax = plt.subplots(figsize=(14, 7))
        ax.imshow(wc, interpolation="bilinear")
        ax.axis("off")
        ax.set_title("뉴스 텍스트 WordCloud", fontsize=14, fontweight="bold")
        plt.tight_layout()
        fig.savefig(EDA_DIR / "wordcloud.png", dpi=150, bbox_inches="tight")
        plt.close(fig)
        print("  ✅ wordcloud.png")
    except Exception as e:
        print(f"  ⚠️  WordCloud 생성 실패: {e}")

    print(f"[EDA] 완료 → {EDA_DIR}")


# ══════════════════════════════════════════════════════════════════════════════
# 7. ML 모델 학습
# ══════════════════════════════════════════════════════════════════════════════
def train_ml_models(ml_df: pd.DataFrame):
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model    import LogisticRegression
    from sklearn.ensemble        import RandomForestClassifier
    from sklearn.tree            import DecisionTreeClassifier
    from sklearn.pipeline        import Pipeline
    from sklearn.preprocessing   import FunctionTransformer
    from scipy.sparse            import hstack, csr_matrix

    print("\n[ML] 모델 학습 시작...")

    X_text = ml_df["text"].fillna("")
    X_num  = ml_df[["keyword_count","text_length","keyword_length",
                     "has_investment_word","has_saving_word","has_risk_word"]].fillna(0).values
    y      = ml_df["label"].values

    # TF-IDF (char_wb, ngram 2~4)
    tfidf = TfidfVectorizer(
        analyzer="char_wb",
        ngram_range=(2, 4),
        max_features=3000,
        sublinear_tf=True,
    )
    X_tfidf = tfidf.fit_transform(X_text)
    X_all   = hstack([X_tfidf, csr_matrix(X_num)])

    n_samples = len(y)
    n_pos     = int(y.sum())
    n_neg     = n_samples - n_pos
    print(f"  학습 데이터: {n_samples}건  label=1: {n_pos}  label=0: {n_neg}")

    models = {
        "Logistic Regression": LogisticRegression(max_iter=1000, class_weight="balanced", C=1.0),
        "Random Forest":       RandomForestClassifier(n_estimators=100, class_weight="balanced", random_state=42),
        "Decision Tree":       DecisionTreeClassifier(max_depth=6, class_weight="balanced", random_state=42),
    }

    return tfidf, X_all, y, models


# ══════════════════════════════════════════════════════════════════════════════
# 8. 평가
# ══════════════════════════════════════════════════════════════════════════════
def evaluate_models(tfidf, X_all, y, models: dict) -> dict:
    from sklearn.model_selection  import StratifiedKFold, cross_val_predict
    from sklearn.metrics          import (accuracy_score, precision_score, recall_score,
                                          f1_score, confusion_matrix, classification_report)
    from scipy.sparse             import hstack, csr_matrix

    print("\n[평가] 교차검증 (Stratified 5-fold)...")
    n = len(y)
    n_splits = min(5, max(2, n // 4))  # 데이터 수에 맞게 fold 조정

    results   = {}
    all_preds = {}

    for name, clf in models.items():
        skf  = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=42)
        pred = cross_val_predict(clf, X_all, y, cv=skf)
        all_preds[name] = pred

        acc  = accuracy_score(y, pred)
        prec = precision_score(y, pred, zero_division=0)
        rec  = recall_score(y, pred, zero_division=0)
        f1   = f1_score(y, pred, zero_division=0)
        cm   = confusion_matrix(y, pred)
        cr   = classification_report(y, pred, target_names=["비친화(0)","아이 친화(1)"], zero_division=0)

        results[name] = {
            "accuracy": acc, "precision": prec,
            "recall":   rec, "f1":        f1,
            "cm":       cm,  "report":    cr,
            "pred":     pred,
        }
        print(f"  {name:25s}  Acc={acc:.3f}  F1={f1:.3f}")

    # ── 지표 CSV ──────────────────────────────────────────────────────────────
    metric_rows = []
    for name, r in results.items():
        metric_rows.append({
            "model":     name,
            "accuracy":  round(r["accuracy"], 4),
            "precision": round(r["precision"], 4),
            "recall":    round(r["recall"], 4),
            "f1_score":  round(r["f1"], 4),
        })
    metrics_df = pd.DataFrame(metric_rows)
    metrics_df.to_csv(ML_DIR / "model_metrics.csv", index=False, encoding="utf-8-sig")

    # ── Classification Report txt ─────────────────────────────────────────────
    with open(ML_DIR / "classification_report.txt", "w", encoding="utf-8") as f:
        for name, r in results.items():
            f.write(f"{'='*60}\n{name}\n{'='*60}\n")
            f.write(r["report"] + "\n\n")

    # ── Confusion Matrix 그래프 ───────────────────────────────────────────────
    n_models = len(models)
    fig, axes = plt.subplots(1, n_models, figsize=(6 * n_models, 5))
    if n_models == 1:
        axes = [axes]
    for ax, (name, r) in zip(axes, results.items()):
        sns.heatmap(r["cm"], annot=True, fmt="d", cmap="Blues", ax=ax,
                    xticklabels=["비친화(0)","친화(1)"],
                    yticklabels=["비친화(0)","친화(1)"])
        ax.set_title(f"{name}\nAcc={r['accuracy']:.3f}  F1={r['f1']:.3f}", fontsize=11)
        ax.set_xlabel("예측값")
        ax.set_ylabel("실제값")
    plt.suptitle("Confusion Matrix 비교", fontsize=14, fontweight="bold", y=1.02)
    plt.tight_layout()
    fig.savefig(ML_DIR / "confusion_matrix.png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  ✅ confusion_matrix.png")

    return results


# ══════════════════════════════════════════════════════════════════════════════
# 9. 발표용 요약 리포트 저장
# ══════════════════════════════════════════════════════════════════════════════
def save_outputs(news_df: pd.DataFrame, label_df: pd.DataFrame,
                 kw_ml: pd.DataFrame, results: dict):
    best_name = max(results, key=lambda k: results[k]["f1"])
    best      = results[best_name]

    # ── 오분류 사례 ───────────────────────────────────────────────────────────
    mis_rows = []
    y_true = kw_ml["label"].values
    y_pred = results[best_name]["pred"]
    for i, (yt, yp) in enumerate(zip(y_true, y_pred)):
        if yt != yp and i < len(kw_ml):
            row = kw_ml.iloc[i]
            mis_rows.append({
                "keyword":    row.get("keyword",""),
                "실제 라벨": yt,
                "예측 라벨": yp,
                "텍스트 앞 50자": str(row["text"])[:50],
            })
    mis_df = pd.DataFrame(mis_rows[:10])

    # ── EDA 요약 텍스트 ───────────────────────────────────────────────────────
    from collections import Counter
    all_kws = []
    for t in news_df["text"]:
        all_kws.extend(extract_economic_keywords(t))
    top5 = Counter(all_kws).most_common(5)

    # ── ml_summary.md 작성 ───────────────────────────────────────────────────
    md_lines = [
        "# 크롤링 뉴스 텍스트 기반 ML 파이프라인 — 발표 요약",
        "",
        "## 1. 사용 데이터 개요",
        f"| 항목 | 값 |",
        f"|---|---|",
        f"| 크롤링 기사 수 | {len(news_df)}건 |",
        f"| 전처리 후 기사 수 | {len(news_df)}건 |",
        f"| 라벨 키워드 수 | {len(label_df)}개 |",
        f"| ML 학습 샘플 수 | {len(kw_ml)}건 |",
        f"| label=1 (아이 친화) | {int(label_df['label'].sum())}개 |",
        f"| label=0 (비친화) | {int((label_df['label']==0).sum())}개 |",
        "",
        "## 2. 전처리 내용",
        "- HTML 태그 제거 (`re.sub`)",
        "- HTML 엔티티 복원 (`html.unescape`)",
        "- 이메일 주소 제거",
        "- 기자명 패턴 제거 (`[가-힣]{2,4} 기자`)",
        "- 저작권·광고성 문구 제거",
        "- 특수문자 제거 (한글·영문·숫자·공백 유지)",
        "- 단독 숫자 토큰 제거",
        "- 20자 미만 텍스트 제거",
        "- 중복 기사 제거 (`drop_duplicates`)",
        "",
        "## 3. EDA 결과 요약",
        f"- 전체 기사에서 추출된 경제 키워드 총 {len(all_kws)}건",
        f"- Top 5 키워드: {', '.join([f'{k}({c})' for k,c in top5])}",
        "- 저장 그래프: top20_keywords, label_distribution, topic_distribution,",
        "  text_length_distribution, wordcloud",
        "",
        "## 4. 사용한 ML 모델",
        "| 모델 | 특징 |",
        "|---|---|",
        "| Logistic Regression | 선형 분류, 빠르고 해석 용이 |",
        "| Random Forest | 앙상블, 과적합 방지 |",
        "| Decision Tree | 규칙 기반, 시각화 쉬움 |",
        "",
        "**텍스트 벡터화**: TF-IDF (`analyzer=char_wb`, `ngram_range=(2,4)`, `max_features=3000`)",
        "",
        "**추가 수치 피처**: keyword_count, text_length, keyword_length,",
        "  has_investment_word, has_saving_word, has_risk_word",
        "",
        "**평가 방법**: Stratified K-Fold 교차검증",
        "",
        "## 5. 모델 성능 결과",
        "| 모델 | Accuracy | Precision | Recall | F1-score |",
        "|---|---|---|---|---|",
    ]
    for name, r in results.items():
        md_lines.append(
            f"| {name} | {r['accuracy']:.3f} | {r['precision']:.3f} | {r['recall']:.3f} | {r['f1']:.3f} |"
        )
    md_lines += [
        "",
        f"## 6. 최고 성능 모델",
        f"**{best_name}** (F1-score: {best['f1']:.3f})",
        "",
        "## 7. 오분류 사례",
    ]
    if len(mis_df) > 0:
        md_lines.append("| 키워드 | 실제 | 예측 | 텍스트 앞 50자 |")
        md_lines.append("|---|---|---|---|")
        for _, row in mis_df.iterrows():
            md_lines.append(f"| {row['keyword']} | {row['실제 라벨']} | {row['예측 라벨']} | {row['텍스트 앞 50자']} |")
    else:
        md_lines.append("오분류 없음 (완벽한 분류 또는 단일 클래스)")
    md_lines += [
        "",
        "## 8. 서비스 적용 방식",
        "> 크롤링한 금융뉴스 텍스트를 전처리한 뒤 TF-IDF로 벡터화하고,",
        "> 머신러닝 모델을 통해 뉴스 속 경제 단어가 아이용 금융교육에 적합한지 분류했다.",
        "> 모델 성능은 Accuracy와 F1-score로 확인했으며,",
        "> 분류 결과는 아이에게 보여줄 금융 개념 선정과 LLM 설명 생성 단계에 활용된다.",
        "",
        "---",
        "*Generated by text_ml_pipeline.py*",
    ]

    with open(ML_DIR / "ml_summary.md", "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines))
    print(f"  ✅ ml_summary.md")


# ══════════════════════════════════════════════════════════════════════════════
# main
# ══════════════════════════════════════════════════════════════════════════════
def main():
    t0 = time.time()
    print("=" * 60)
    print("크롤링 뉴스 텍스트 기반 ML 파이프라인")
    print("=" * 60)

    # 1. 데이터 로드
    print("\n[STEP 1] 뉴스 데이터 로드")
    news_df = load_news_data()

    # 2. 전처리
    print("\n[STEP 2] 텍스트 전처리")
    news_df = preprocess_df(news_df)

    # 3. 경제 키워드 추출
    print("\n[STEP 3] 경제 키워드 추출")
    news_df["matched_keywords"] = news_df["text"].apply(extract_economic_keywords)
    news_df["keyword_count"]    = news_df["matched_keywords"].apply(len)
    has_kw = news_df["keyword_count"] > 0
    print(f"  키워드 포함 기사: {has_kw.sum()}건 / 전체 {len(news_df)}건")
    news_kw_df = news_df[has_kw].reset_index(drop=True)

    # 4. 라벨 데이터
    print("\n[STEP 4] 라벨 데이터 로드")
    label_df = build_labeled_dataset()

    # 5. ML 학습 데이터
    print("\n[STEP 5] ML 학습 데이터 생성")
    kw_ml, art_ml = build_ml_dataset(news_kw_df, label_df)

    # 6. EDA
    print("\n[STEP 6] EDA")
    run_eda(news_kw_df if len(news_kw_df) > 0 else news_df, label_df)

    # 7-8. 학습 & 평가
    print("\n[STEP 7-8] ML 학습 & 평가")
    if len(kw_ml) < 6:
        print("  ⚠️  학습 데이터 6건 미만. 라벨 데이터만으로 학습합니다.")
        kw_ml = label_df.copy()
        kw_ml["text"] = kw_ml["keyword"]
        kw_ml["keyword_count"] = 1
        kw_ml["text_length"]   = kw_ml["keyword"].str.len()
        kw_ml["keyword_length"] = kw_ml["keyword"].str.len()
        kw_ml["has_investment_word"] = kw_ml["keyword"].apply(lambda x: int(x in INVEST_WORDS))
        kw_ml["has_saving_word"]     = kw_ml["keyword"].apply(lambda x: int(x in SAVING_WORDS))
        kw_ml["has_risk_word"]       = kw_ml["keyword"].apply(lambda x: int(x in RISK_WORDS))

    tfidf, X_all, y, models = train_ml_models(kw_ml)
    results = evaluate_models(tfidf, X_all, y, models)

    # 9. 발표 리포트 저장
    print("\n[STEP 9] 발표용 리포트 저장")
    save_outputs(news_df, label_df, kw_ml, results)

    # ── 최종 요약 ─────────────────────────────────────────────────────────────
    elapsed = time.time() - t0
    best_name = max(results, key=lambda k: results[k]["f1"])
    best_r    = results[best_name]

    print("\n" + "=" * 60)
    print("실행 완료 요약")
    print("=" * 60)
    print(f"\n생성한 파일:")
    for p in sorted((ML_DIR / "..").rglob("*.csv")) + sorted((ML_DIR / "..").rglob("*.png")) + \
             sorted((ML_DIR / "..").rglob("*.txt")) + sorted((ML_DIR / "..").rglob("*.md")):
        if p.is_file() and ("outputs" in str(p) or "child_friendly" in str(p)):
            print(f"  {p.relative_to(BASE_DIR)}")

    print(f"\n전처리: HTML태그·기자명·저작권 제거, 특수문자 정리, 중복 제거")
    print(f"EDA 그래프: top20_keywords / label_distribution / topic_distribution / text_length_distribution / wordcloud")
    print(f"ML 모델: Logistic Regression / Random Forest / Decision Tree")
    print(f"\n성능 결과:")
    for name, r in results.items():
        print(f"  {name:25s}  Acc={r['accuracy']:.3f}  F1={r['f1']:.3f}")
    print(f"\n최고 모델: {best_name}  (Acc={best_r['accuracy']:.3f}  F1={best_r['f1']:.3f})")
    print(f"\n발표용 한 줄 설명:")
    print("  크롤링한 금융뉴스 텍스트를 전처리한 뒤 TF-IDF로 벡터화하고,")
    print("  머신러닝 모델을 통해 뉴스 속 경제 단어가 아이용 금융교육에")
    print("  적합한지 분류했다. 최고 성능 모델은 " + best_name + f"로")
    print(f"  Accuracy {best_r['accuracy']:.1%}, F1-score {best_r['f1']:.1%}를 달성했다.")
    print(f"\n총 소요 시간: {elapsed:.1f}s")


if __name__ == "__main__":
    main()
