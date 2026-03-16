import streamlit as st
import pandas as pd
import requests
import plotly.express as px
import plotly.graph_objects as go
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from datetime import datetime, timedelta
from collections import Counter
import re
import time

# ─────────────────────────────────────────────
# Page Config
# ─────────────────────────────────────────────
st.set_page_config(
    page_title="한국 영화 흥행 비교 대시보드",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ─────────────────────────────────────────────
# API Keys
# ─────────────────────────────────────────────
try:
    KOBIS_API_KEY = st.secrets["KOBIS_API_KEY"]
    TMDB_API_KEY = st.secrets["TMDB_API_KEY"]
    YOUTUBE_API_KEY = st.secrets["YOUTUBE_API_KEY"]
except KeyError as e:
    st.error(f"API Key가 설정되지 않았습니다: {e}")
    st.stop()

# ─────────────────────────────────────────────
# Movie Configuration
# ─────────────────────────────────────────────
ALL_MOVIES = ["왕과 사는 남자", "명량", "사도", "기생충"]

MOVIE_MAP = {
    "왕과 사는 남자": {"tmdb_id": 1321179, "kobis_nm": "왕과 사는 남자"},
    "명량":          {"tmdb_id": 283566,  "kobis_nm": "명량"},
    "사도":          {"tmdb_id": 318049,  "kobis_nm": "사도"},
    "기생충":        {"tmdb_id": 496243,  "kobis_nm": "기생충"},
}

# 포커스 영화 강조 색상
FOCUS_COLOR   = "#FF4B4B"
OTHERS_COLOR  = "#AAAAAA"

VIDEO_TYPE_RULES = {
    "예고편":     ["예고편", "trailer", "티저", "teaser", "공식"],
    "리뷰/해설":  ["리뷰", "review", "해석", "해설", "결말", "총정리", "분석", "스포"],
    "명장면/클립": ["명장면", "클립", "clip", "scene", "ost", "비하인드", "메이킹"],
    "인터뷰/홍보": ["인터뷰", "interview", "홍보", "무대인사", "시사회"],
}

def classify_video(title: str) -> str:
    t = title.lower()
    for vtype, kws in VIDEO_TYPE_RULES.items():
        if any(k in t for k in kws):
            return vtype
    return "기타"

def movie_colors(titles, focus):
    return [FOCUS_COLOR if t == focus else OTHERS_COLOR for t in titles]

# ─────────────────────────────────────────────
# API Fetchers
# ─────────────────────────────────────────────

@st.cache_data(ttl=3600)
def fetch_tmdb(movie_id: int):
    url = f"https://api.themoviedb.org/3/movie/{movie_id}"
    try:
        r = requests.get(url, params={"api_key": TMDB_API_KEY, "language": "ko-KR"}, timeout=5)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return {}

@st.cache_data(ttl=3600)
def fetch_kobis(movie_nm: str, days: int = 20):
    url = "http://www.kobis.or.kr/kobisopenapi/webservice/rest/boxoffice/searchDailyBoxOfficeList.json"
    data = []
    for i in range(1, days + 1):
        dt = (datetime.now() - timedelta(days=i)).strftime("%Y%m%d")
        try:
            r = requests.get(url, params={"key": KOBIS_API_KEY, "targetDt": dt}, timeout=5)
            if r.status_code == 200:
                lst = r.json().get("boxOfficeResult", {}).get("dailyBoxOfficeList", [])
                row = next((m for m in lst if m["movieNm"] == movie_nm), None)
                if row:
                    data.append({
                        "movie_title": movie_nm,
                        "날짜": pd.to_datetime(dt),
                        "일일 관객수": int(row["audiCnt"]),
                        "누적 관객수": int(row["audiAcc"]),
                        "스크린 수":  int(row["scrnCnt"]),
                        "상영 횟수":  int(row["showCnt"]),
                    })
        except Exception:
            pass
        time.sleep(0.05)
    return pd.DataFrame(data).sort_values("날짜") if data else pd.DataFrame()

@st.cache_data(ttl=3600)
def fetch_yt_videos(movie_title: str):
    queries = [
        movie_title, f"{movie_title} 예고편", f"{movie_title} 리뷰",
        f"{movie_title} 해석", f"{movie_title} 명장면", f"{movie_title} trailer",
    ]
    try:
        yt = build("youtube", "v3", developerKey=YOUTUBE_API_KEY)
        seen, ids = set(), []
        for q in queries:
            try:
                res = yt.search().list(q=q, part="id,snippet", maxResults=5, type="video").execute()
                for item in res.get("items", []):
                    vid = item["id"]["videoId"]
                    if vid not in seen:
                        seen.add(vid)
                        ids.append(vid)
            except HttpError:
                continue

        rows = []
        for i in range(0, len(ids), 50):
            batch = ids[i:i+50]
            try:
                vres = yt.videos().list(id=",".join(batch), part="snippet,statistics").execute()
                for item in vres.get("items", []):
                    s = item.get("snippet", {})
                    st_ = item.get("statistics", {})
                    title = s.get("title", "")
                    if movie_title not in title:
                        continue
                    rows.append({
                        "movie_title": movie_title,
                        "video_id":    item["id"],
                        "title":       title,
                        "channel":     s.get("channelTitle", ""),
                        "published":   s.get("publishedAt", "")[:10],
                        "view_count":  int(st_.get("viewCount", 0)),
                        "like_count":  int(st_.get("likeCount", 0)),
                        "comment_count": int(st_.get("commentCount", 0)),
                        "유형": classify_video(title),
                    })
            except HttpError:
                continue
        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame(rows).drop_duplicates("video_id")
        return df.sort_values("view_count", ascending=False).reset_index(drop=True)
    except Exception as e:
        return pd.DataFrame()

@st.cache_data(ttl=3600)
def fetch_yt_comments(video_ids: tuple):
    yt = build("youtube", "v3", developerKey=YOUTUBE_API_KEY)
    comments = []
    for vid in video_ids:
        try:
            res = yt.commentThreads().list(videoId=vid, part="snippet", maxResults=50).execute()
            for item in res.get("items", []):
                comments.append(item["snippet"]["topLevelComment"]["snippet"]["textDisplay"])
        except HttpError:
            continue
    return comments

def top_keywords(comments, n=20):
    stop = {"이", "그", "를", "을", "가", "의", "에", "은", "는", "도", "와",
            "과", "한", "ㅋㅋ", "ㅎㅎ", "ㅜㅜ", "ㅠㅠ", "진짜", "정말", "너무",
            "이거", "그냥", "좀", "것", "수"}
    words = []
    for c in comments:
        words += [w for w in re.findall(r"[가-힣]{2,}", c) if w not in stop]
    return pd.DataFrame(Counter(words).most_common(n), columns=["키워드", "횟수"])

# ─────────────────────────────────────────────
# Load ALL movie data upfront
# ─────────────────────────────────────────────
@st.cache_data(ttl=3600)
def load_all_tmdb():
    result = {}
    for nm, cfg in MOVIE_MAP.items():
        result[nm] = fetch_tmdb(cfg["tmdb_id"])
    return result

@st.cache_data(ttl=3600)
def load_all_kobis():
    frames = []
    for nm, cfg in MOVIE_MAP.items():
        df = fetch_kobis(cfg["kobis_nm"], days=20)
        if not df.empty:
            frames.append(df)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

@st.cache_data(ttl=3600)
def load_all_yt():
    frames = []
    for nm in ALL_MOVIES:
        df = fetch_yt_videos(nm)
        if not df.empty:
            frames.append(df)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

# ─────────────────────────────────────────────
# Sidebar
# ─────────────────────────────────────────────
st.sidebar.title("🎬 영화 흥행 비교 대시보드")
st.sidebar.markdown("비교 기준 영화를 선택하면\n나머지 3편과 자동으로 비교합니다.")
focus = st.sidebar.selectbox("🔍 포커스 영화 선택", ALL_MOVIES, index=0)
others = [m for m in ALL_MOVIES if m != focus]

st.sidebar.divider()
st.sidebar.caption("Data: KOBIS | TMDB | YouTube Data API v3")

# ─────────────────────────────────────────────
# Load Data
# ─────────────────────────────────────────────
with st.spinner("모든 영화 데이터를 불러오는 중... (최초 로드 시 시간이 소요될 수 있습니다)"):
    all_tmdb  = load_all_tmdb()
    df_kobis  = load_all_kobis()
    df_yt_all = load_all_yt()

# TMDB 요약 테이블 생성
tmdb_rows = []
for nm, d in all_tmdb.items():
    tmdb_rows.append({
        "movie_title": nm,
        "vote_average": d.get("vote_average", 0),
        "popularity":   d.get("popularity", 0),
        "runtime":      d.get("runtime", 0),
        "budget":       d.get("budget", 0),
        "release_date": d.get("release_date", ""),
        "tagline":      d.get("tagline", ""),
        "genres":       ", ".join([g["name"] for g in d.get("genres", [])]),
    })
df_tmdb = pd.DataFrame(tmdb_rows)

# YouTube 집계 (영화별 총계)
if not df_yt_all.empty:
    yt_agg = df_yt_all.groupby("movie_title").agg(
        total_views=("view_count", "sum"),
        total_likes=("like_count", "sum"),
        total_comments=("comment_count", "sum"),
        video_count=("video_id", "count"),
    ).reset_index()
else:
    yt_agg = pd.DataFrame()

# ─────────────────────────────────────────────
# Main Title
# ─────────────────────────────────────────────
st.title("🎥 한국 영화 흥행 성공 요인 비교 분석")
st.markdown(
    f"기준 영화 **:red[{focus}]** 를 나머지 영화 "
    f"({', '.join(others)})와 비교 분석합니다."
)
st.divider()

# ─────────────────────────────────────────────
# Tabs
# ─────────────────────────────────────────────
tab1, tab2, tab3 = st.tabs(["📊 전체 비교", "📈 흥행 추이", "📺 YouTube 분석"])

# ══════════════════════════════════════════════
# TAB 1: 전체 비교
# ══════════════════════════════════════════════
with tab1:

    # --- KPI: 포커스 영화 ---
    foc_kobis = df_kobis[df_kobis["movie_title"] == focus]
    foc_tmdb  = df_tmdb[df_tmdb["movie_title"] == focus].iloc[0] if not df_tmdb.empty else {}
    foc_yt    = yt_agg[yt_agg["movie_title"] == focus].iloc[0] if (not yt_agg.empty and focus in yt_agg["movie_title"].values) else {}

    st.subheader(f"🔴 [{focus}] 주요 지표")
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("최근 누적 관객수", f"{foc_kobis['누적 관객수'].max():,}명" if not foc_kobis.empty else "N/A")
    k2.metric("TMDB 평점", f"{foc_tmdb.get('vote_average', 0):.1f} / 10" if isinstance(foc_tmdb, pd.Series) else "N/A")
    k3.metric("YouTube 총 조회수", f"{int(foc_yt.get('total_views', 0)):,}회" if isinstance(foc_yt, pd.Series) else "N/A")
    k4.metric("TMDB 인기도", f"{foc_tmdb.get('popularity', 0):.0f}" if isinstance(foc_tmdb, pd.Series) else "N/A")

    st.divider()

    # --- 1. 누적 관객수 비교 ---
    st.subheader("👥 최근 집계 기준 누적 관객수 비교")
    if not df_kobis.empty:
        latest_acc = df_kobis.groupby("movie_title")["누적 관객수"].max().reset_index()
        colors = movie_colors(latest_acc["movie_title"], focus)
        fig_acc_bar = go.Figure(go.Bar(
            x=latest_acc["movie_title"],
            y=latest_acc["누적 관객수"],
            marker_color=colors,
            text=[f"{v:,}" for v in latest_acc["누적 관객수"]],
            textposition="outside"
        ))
        fig_acc_bar.update_layout(title="영화별 누적 관객수", yaxis_title="누적 관객수")
        st.plotly_chart(fig_acc_bar, use_container_width=True)

    # --- 2. TMDB 평점 + 인기도 비교 ---
    st.subheader("⭐ TMDB 평점 & 인기도 비교")
    if not df_tmdb.empty:
        c1, c2 = st.columns(2)
        with c1:
            colors_v = movie_colors(df_tmdb["movie_title"], focus)
            fig_vote = go.Figure(go.Bar(
                x=df_tmdb["movie_title"], y=df_tmdb["vote_average"],
                marker_color=colors_v,
                text=[f"{v:.1f}" for v in df_tmdb["vote_average"]],
                textposition="outside"
            ))
            fig_vote.update_layout(title="TMDB 평점 비교", yaxis=dict(range=[0, 10]))
            st.plotly_chart(fig_vote, use_container_width=True)
        with c2:
            colors_p = movie_colors(df_tmdb["movie_title"], focus)
            fig_pop = go.Figure(go.Bar(
                x=df_tmdb["movie_title"], y=df_tmdb["popularity"],
                marker_color=colors_p,
                text=[f"{v:.0f}" for v in df_tmdb["popularity"]],
                textposition="outside"
            ))
            fig_pop.update_layout(title="TMDB 인기도 비교")
            st.plotly_chart(fig_pop, use_container_width=True)

    # --- 3. YouTube 총 조회수 비교 ---
    st.subheader("📺 YouTube 관련 영상 총 조회수 비교")
    if not yt_agg.empty:
        colors_yt = movie_colors(yt_agg["movie_title"], focus)
        fig_yt_bar = go.Figure(go.Bar(
            x=yt_agg["movie_title"],
            y=yt_agg["total_views"],
            marker_color=colors_yt,
            text=[f"{int(v):,}" for v in yt_agg["total_views"]],
            textposition="outside"
        ))
        fig_yt_bar.update_layout(title="영화별 YouTube 총 조회수")
        st.plotly_chart(fig_yt_bar, use_container_width=True)

    # --- 4. 영화 메타데이터 비교 테이블 ---
    st.subheader("📋 영화 기본 정보 비교")
    meta_display = df_tmdb[["movie_title", "release_date", "genres", "runtime", "vote_average", "popularity"]].copy()
    meta_display.columns = ["제목", "개봉일", "장르", "러닝타임(분)", "평점", "인기도"]
    st.dataframe(meta_display.set_index("제목"), use_container_width=True)


# ══════════════════════════════════════════════
# TAB 2: 흥행 추이
# ══════════════════════════════════════════════
with tab2:
    st.subheader("📈 영화별 박스오피스 추이 (최근 20일)")

    if df_kobis.empty:
        st.info("박스오피스 데이터를 불러오지 못했습니다.")
    else:
        # 누적 관객수 추이 (모두 겹쳐서 보기) — 포커스 영화 강조
        fig_trend = go.Figure()
        for nm in ALL_MOVIES:
            df_m = df_kobis[df_kobis["movie_title"] == nm]
            if df_m.empty:
                continue
            is_focus = nm == focus
            fig_trend.add_trace(go.Scatter(
                x=df_m["날짜"], y=df_m["누적 관객수"],
                mode="lines+markers",
                name=nm,
                line=dict(
                    width=4 if is_focus else 1.5,
                    color=FOCUS_COLOR if is_focus else None
                ),
                opacity=1.0 if is_focus else 0.5
            ))
        fig_trend.update_layout(title="누적 관객수 성장 곡선 비교", xaxis_title="날짜", yaxis_title="누적 관객수")
        st.plotly_chart(fig_trend, use_container_width=True)

        # 일별 관객수 추이
        fig_daily = go.Figure()
        for nm in ALL_MOVIES:
            df_m = df_kobis[df_kobis["movie_title"] == nm]
            if df_m.empty:
                continue
            is_focus = nm == focus
            fig_daily.add_trace(go.Bar(
                x=df_m["날짜"], y=df_m["일일 관객수"],
                name=nm,
                marker_color=FOCUS_COLOR if is_focus else None,
                opacity=1.0 if is_focus else 0.6
            ))
        fig_daily.update_layout(title="일별 관객수 비교", barmode="group", xaxis_title="날짜", yaxis_title="일일 관객수")
        st.plotly_chart(fig_daily, use_container_width=True)

        # --- 포커스 영화 상세 지표
        st.subheader(f"🔴 [{focus}] 상세 박스오피스 지표")
        foc_df = df_kobis[df_kobis["movie_title"] == focus]
        if not foc_df.empty:
            d1, d2, d3, d4 = st.columns(4)
            d1.metric("최고 일일 관객수", f"{foc_df['일일 관객수'].max():,}명")
            d2.metric("평균 일일 관객수", f"{foc_df['일일 관객수'].mean():,.0f}명")
            d3.metric("최대 스크린 수",   f"{foc_df['스크린 수'].max():,}개")
            d4.metric("최대 상영 횟수",   f"{foc_df['상영 횟수'].max():,}회")
            st.dataframe(foc_df.drop(columns=["movie_title"]).set_index("날짜"), use_container_width=True)


# ══════════════════════════════════════════════
# TAB 3: YouTube 분석
# ══════════════════════════════════════════════
with tab3:
    st.subheader(f"📺 YouTube — 포커스 [{focus}] vs 비교 영화")

    if df_yt_all.empty:
        st.info("YouTube 데이터를 불러오지 못했습니다.")
    else:
        # 영화별 YouTube 집계 비교
        c1, c2, c3 = st.columns(3)
        with c1:
            colors_v = movie_colors(yt_agg["movie_title"], focus)
            fig_v = go.Figure(go.Bar(x=yt_agg["movie_title"], y=yt_agg["total_views"],
                                     marker_color=colors_v,
                                     text=[f"{int(v/1e4):.0f}만" for v in yt_agg["total_views"]],
                                     textposition="outside"))
            fig_v.update_layout(title="총 조회수")
            st.plotly_chart(fig_v, use_container_width=True)
        with c2:
            colors_l = movie_colors(yt_agg["movie_title"], focus)
            fig_l = go.Figure(go.Bar(x=yt_agg["movie_title"], y=yt_agg["total_likes"],
                                     marker_color=colors_l,
                                     text=[f"{int(v):,}" for v in yt_agg["total_likes"]],
                                     textposition="outside"))
            fig_l.update_layout(title="총 좋아요")
            st.plotly_chart(fig_l, use_container_width=True)
        with c3:
            colors_c = movie_colors(yt_agg["movie_title"], focus)
            fig_c = go.Figure(go.Bar(x=yt_agg["movie_title"], y=yt_agg["total_comments"],
                                     marker_color=colors_c,
                                     text=[f"{int(v):,}" for v in yt_agg["total_comments"]],
                                     textposition="outside"))
            fig_c.update_layout(title="총 댓글수")
            st.plotly_chart(fig_c, use_container_width=True)

        st.divider()

        # 영상 유형별 분포 비교
        st.subheader("🎞️ 영상 유형별 조회수 분포 비교")
        type_agg = df_yt_all.groupby(["movie_title", "유형"])["view_count"].sum().reset_index()
        fig_type = px.bar(type_agg, x="유형", y="view_count", color="movie_title",
                          barmode="group", title="영화·유형별 조회수 합계")
        st.plotly_chart(fig_type, use_container_width=True)

        st.divider()

        # 포커스 영화 — 상위 영상 리스트
        st.subheader(f"🔴 [{focus}] 상위 조회수 영상 리스트")
        foc_yt_df = df_yt_all[df_yt_all["movie_title"] == focus].head(10)
        if not foc_yt_df.empty:
            disp = foc_yt_df[["title", "channel", "published", "유형", "view_count", "like_count", "comment_count"]].copy()
            disp.columns = ["제목", "채널", "업로드일", "유형", "조회수", "좋아요", "댓글수"]
            st.dataframe(disp, use_container_width=True, hide_index=True)

            # 댓글 키워드 분석
            st.subheader(f"💬 [{focus}] 상위 3개 영상 댓글 키워드 분석")
            top3 = tuple(foc_yt_df["video_id"].head(3).tolist())
            with st.spinner("댓글을 수집하는 중..."):
                comments = fetch_yt_comments(top3)
            if comments:
                kw_df = top_keywords(comments)
                kw1, kw2 = st.columns([2, 1])
                with kw1:
                    fig_kw = px.bar(kw_df, x="키워드", y="횟수",
                                    title="댓글 키워드 TOP 20", color="횟수")
                    st.plotly_chart(fig_kw, use_container_width=True)
                with kw2:
                    st.dataframe(kw_df, use_container_width=True, hide_index=True)

                st.markdown("**대표 댓글 샘플 (10개)**")
                for i, c in enumerate(comments[:10], 1):
                    st.markdown(f"{i}. {c[:120]}{'...' if len(c) > 120 else ''}")
            else:
                st.info("댓글 데이터를 수집하지 못했습니다.")
        else:
            st.info(f"'{focus}'에 대한 YouTube 영상 데이터가 없습니다.")
