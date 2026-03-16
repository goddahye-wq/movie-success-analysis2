# 영화 '왕과 사는 남자' 천만 달성 성공 요인 분석 프로젝트

본 프로젝트는 영화 '왕과 사는 남자'가 천만 관객을 달성한 성공 요인을 분석하기 위해 기획되었습니다. 주요 라이벌 및 비교 대상 영화인 '명량', '사도', '기생충'과 데이터를 비교 분석하여 성공 전략을 도출합니다.

## 프로젝트 구조

- `movie_success_analysis/`
    - `data/`: 분석에 사용되는 데이터 저장소
        - `raw/`: 수집된 원본 데이터 (KOBIS, TMDB, SNS 등)
        - `processed/`: 전처리 및 정제된 데이터
    - `notebooks/`: EDA 및 주요 분석 작업용 Jupyter Notebook
    - `scripts/`: 데이터 수집(Scraping, API 호출) 및 전처리를 위한 Python 스크립트
    - `reports/`: 시각화 결과 및 최종 분석 보고서

## 분석 대상 영화
1. **왕과 사는 남자** (분석 대상)
2. **명량** (역대 최고 관객수 기록)
3. **사도** (사극 장르 비교)
4. **기생충** (글로벌 성공 및 평단 반응 비교)

## 주요 분석 지표
- 주차별 관객수 및 점유율 (Box Office)
- 장르 및 제작비 대비 수익성
- 주요 키워드 및 SNS 반응 (감성 분석 등)
- 배우 및 감독의 과거 성과 데이터
- 개봉 당시 경쟁작 현황

## 기술 스택
- **언어**: Python
- **데이터 분석**: Pandas
- **시각화**: Matplotlib (with `koreanize-matplotlib`), Seaborn, Plotly
- **데이터 수집**: Selenium, BeautifulSoup4, Requests, Google API
- **환경**: Jupyter Notebook, `uv` (가상환경 관리)

## 실행 방법

1. 의존성 설치:
   ```bash
   uv sync
   ```
2. 분석 실행:
   - `notebooks/` 내부의 노트북 파일을 실행합니다.
