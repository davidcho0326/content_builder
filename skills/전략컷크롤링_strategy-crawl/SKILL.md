---
name: strategy-crawl
description: 브랜드 공식몰 + 인스타그램 이미지 크롤링. 전략실컷빌더 파이프라인 Step 1.
user-invocable: true
trigger-keywords: ["전략컷 크롤링", "브랜드 크롤링", "strategy crawl", "이미지 수집"]
---

# 전략컷 크롤링 (Strategy Crawl)

> 브랜드 공식몰 + Instagram에서 제품/마케팅 이미지를 수집한다.
> 수집된 이미지는 DNA 분석의 입력이 된다.

---

## 절대 규칙

1. **병렬 다운로드 필수** — `ThreadPoolExecutor(max_workers=10)` 사용, 순차 다운로드 금지
2. **중복 방지** — 이미 다운로드된 파일은 스킵 (파일명 기준)
3. **저장 경로 고정** — `db/strategy-cut-builder/{brand}/official-site/` 및 `instagram/`

---

## 입력

| 입력 | 필수 | 형식 | 예시 |
|------|------|------|------|
| 브랜드명 | O | 문자열 | `duvetica`, `mlb`, `discovery` |
| 공식몰 URL | O | URL | `https://www.duvetica.com/ww/collection/` |
| Instagram 핸들 | △ | 문자열 | `duvetica_official` |

---

## 출력

```
db/strategy-cut-builder/{brand}/
├── official-site/         # 공식몰 제품/마케팅 이미지
│   ├── img_001.jpg
│   ├── img_002.jpg
│   └── ...
└── instagram/             # 인스타그램 게시물 이미지
    ├── post_001.jpg
    ├── post_002.jpg
    └── ...
```

---

## 실행 파이프라인

```
1. 브랜드 정보 수집 (AskUserQuestion)
   ├── 브랜드명
   ├── 공식몰 URL
   └── Instagram 핸들 (선택)
       ↓
2. 공식몰 크롤링
   ├── 컬렉션 페이지 HTML 파싱
   ├── 이미지 URL 추출 (srcset, data-src, og:image)
   └── ThreadPoolExecutor 병렬 다운로드
       ↓
3. Instagram 크롤링 (선택)
   ├── 게시물 페이지 접근 (og:image meta tag)
   ├── 이미지 URL 추출
   └── ThreadPoolExecutor 병렬 다운로드
       ↓
4. 결과 보고
   ├── 다운로드 성공/실패 수
   └── 저장 경로 안내
```

---

## 크롤링 기법

### 공식몰 크롤링

```python
# 필수 import
import requests
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

# User-Agent 필수 (봇 차단 방지)
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

# 이미지 URL 추출 패턴
# 1. <img srcset="..."> 에서 가장 큰 해상도
# 2. <img data-src="..."> lazy-load
# 3. <meta property="og:image" content="...">
```

### Instagram og:image 추출

```python
# Instagram 게시물 페이지에서 og:image 추출
# 로그인 불필요 — 공개 게시물의 meta tag 접근
def extract_og_image(post_url: str) -> str:
    resp = requests.get(post_url, headers=HEADERS, timeout=10)
    soup = BeautifulSoup(resp.text, "html.parser")
    og_img = soup.find("meta", property="og:image")
    return og_img["content"] if og_img else None
```

### 병렬 다운로드

```python
def download_image(url: str, save_path: Path) -> bool:
    if save_path.exists():
        return True  # 중복 스킵
    resp = requests.get(url, headers=HEADERS, timeout=30)
    if resp.status_code == 200:
        save_path.write_bytes(resp.content)
        return True
    return False

# 반드시 병렬 실행
with ThreadPoolExecutor(max_workers=10) as executor:
    futures = {
        executor.submit(download_image, url, path): url
        for url, path in download_tasks
    }
    for future in as_completed(futures):
        url = futures[future]
        try:
            success = future.result()
            print(f"[OK] {url}" if success else f"[SKIP] {url}")
        except Exception as e:
            print(f"[ERROR] {url}: {e}")
```

---

## 백엔드 스크립트

| 스크립트 | 역할 |
|---------|------|
| `scripts/strategy_cut_builder/crawl_duvetica.py` | 듀베티카 공식몰 크롤링 |
| `scripts/strategy_cut_builder/download_duvetica.py` | 듀베티카 이미지 다운로드 |
| `scripts/strategy_cut_builder/download_duvetica_instagram.py` | 듀베티카 인스타그램 다운로드 |
| `scripts/strategy_cut_builder/download_duvetica_instagram_v2.py` | 인스타 v2 (og:image) |

---

## 금지 패턴

```python
# FORBIDDEN: 순차 다운로드
for url in image_urls:
    download_image(url)
    time.sleep(1)

# FORBIDDEN: 저장 경로 임의 변경
save_dir = Path("downloads/duvetica/")  # db/strategy-cut-builder/ 아님

# FORBIDDEN: User-Agent 미설정
requests.get(url)  # 봇 차단됨
```

---

## 실행 방법

```bash
# 듀베티카 공식몰 크롤링
PYTHONPATH=. .venv/Scripts/python scripts/strategy_cut_builder/crawl_duvetica.py

# 이미지 다운로드
PYTHONPATH=. .venv/Scripts/python scripts/strategy_cut_builder/download_duvetica.py
```

---

## 에러 처리

| 에러 | 처리 |
|------|------|
| 403 Forbidden | User-Agent 변경 후 재시도 |
| 429 Rate Limit | 5초 대기 후 재시도 (최대 3회) |
| Timeout | 30초 타임아웃, 실패 로그 후 스킵 |
| SSL Error | verify=False 허용 (내부 크롤링 한정) |
