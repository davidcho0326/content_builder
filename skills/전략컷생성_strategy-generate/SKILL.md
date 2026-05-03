---
name: strategy-generate
description: 프롬프트 온리로 Gemini + GPT Image 2 병렬 이미지 생성. 전략실컷빌더 Step 4.
user-invocable: true
trigger-keywords: ["전략컷 생성", "strategy generate", "캠페인 이미지 생성", "전략컷 이미지"]
---

# 전략컷 생성 (Strategy Generate)

> 프롬프트 텍스트만으로 Gemini + GPT Image 2를 병렬 호출하여 이미지를 생성한다.
> **프롬프트 온리 생성** — 레퍼런스 이미지를 API 인풋으로 넣지 않는다 (검증된 접근법).

---

## 절대 규칙

1. **프롬프트 온리 생성** — 레퍼런스 이미지 인풋 사용 금지 (검증 완료)
2. **Gemini + GPT 병렬 실행** — `ThreadPoolExecutor` 사용, 순차 실행 금지
3. **3:4 세로 고정** — 가로형 절대 금지
4. **WORKFLOW_BYPASS_OK 마커** — 스크립트 상위 50줄 내 마커 필수 (코어 워크플로 우회 허용)

---

## 입력

| 입력 | 필수 | 형식 | 예시 |
|------|------|------|------|
| 프롬프트 텍스트 | O | 문자열 or 파일 | `_prompt.txt` |
| 출력 폴더 경로 | O | 경로 | `Fnf_studio_outputs/strategy-cut-builder/duvetica/` |
| 브랜드명 | O | 문자열 | `duvetica` |
| 컷 유형 | O | campaign / influencer | `campaign` |

---

## 출력

```
Fnf_studio_outputs/strategy-cut-builder/{brand}/{timestamp}_{type}/
├── images/
│   ├── scene_01_gemini.png       # Gemini 생성 결과
│   ├── scene_01_gpt.png          # GPT Image 2 생성 결과
│   ├── scene_02_gemini.png
│   ├── scene_02_gpt.png
│   └── _00_reference.jpg         # 추구미 레퍼런스 (참고용 복사)
├── _prompt.txt                    # 사용된 프롬프트 전문
├── config.json                    # 생성 설정
└── prompt.json                    # 프롬프트 JSON
```

---

## 모델 설정

### Gemini

```python
from core.config import IMAGE_MODEL
from core.api import generate_image_to_pil

# Gemini 설정
# model: IMAGE_MODEL (gemini-3-pro-image-preview)
# temperature: 1.0 (다양성 확보)
# aspect_ratio: "3:4"
# 해상도: 2K (기본)
```

### GPT Image 2

```python
from core.config import IMAGE_MODEL_GPT
from core.model_utils import generate_gpt_image
from core.options import get_gpt_size, get_gpt_quality

# GPT 설정
# model: IMAGE_MODEL_GPT (gpt-image-2)
# quality: "high" (~291원/장)
# aspect_ratio: "3:4" → 1024x1536
```

---

## 실행 파이프라인

```
1. 프롬프트 로드 (텍스트 or _prompt.txt)
       ↓
2. 출력 폴더 생성
   Fnf_studio_outputs/strategy-cut-builder/{brand}/{YYYYMMDD_HHMMSS}_{type}/
       ↓
3. 씬별 병렬 생성
   ├── Gemini: generate_image_to_pil(prompt, aspect_ratio="3:4", temperature=1.0)
   └── GPT: generate_gpt_image(prompt, size="1024x1536", quality="high")
   → ThreadPoolExecutor(max_workers=5)
       ↓
4. 결과 저장
   ├── images/{scene_id}_gemini.png
   ├── images/{scene_id}_gpt.png
   ├── _prompt.txt (프롬프트 전문)
   ├── config.json (설정)
   └── prompt.json (프롬프트 JSON)
       ↓
5. 결과 보고 (인풋 + 프롬프트 + 아웃풋 표시)
```

---

## 병렬 생성 패턴

```python
from concurrent.futures import ThreadPoolExecutor, as_completed
from core.api import generate_image_to_pil, _get_next_api_key
from core.model_utils import generate_gpt_image

def generate_scene(scene_id: str, prompt: str, output_dir: Path):
    """Gemini + GPT 동시 생성"""
    results = {}

    def gen_gemini():
        img = generate_image_to_pil(
            prompt=prompt,
            aspect_ratio="3:4",
            temperature=1.0,
        )
        path = output_dir / "images" / f"{scene_id}_gemini.png"
        img.save(path)
        return path

    def gen_gpt():
        img = generate_gpt_image(
            prompt=prompt,
            size="1024x1536",
            quality="high",
        )
        path = output_dir / "images" / f"{scene_id}_gpt.png"
        img.save(path)
        return path

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = {
            executor.submit(gen_gemini): "gemini",
            executor.submit(gen_gpt): "gpt",
        }
        for future in as_completed(futures):
            model = futures[future]
            try:
                results[model] = future.result()
            except Exception as e:
                print(f"[ERROR] {scene_id}_{model}: {e}")

    return results

# 다수 씬 병렬 실행
MAX_WORKERS = 5  # API 키 5개 로테이션 활용

with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
    futures = {
        executor.submit(generate_scene, scene["id"], scene["prompt"], output_dir): scene
        for scene in scenes
    }
    for future in as_completed(futures):
        scene = futures[future]
        results = future.result()
```

---

## config.json 형식

```json
{
  "workflow": "strategy-cut-builder",
  "brand": "duvetica",
  "cut_type": "campaign",
  "timestamp": "2026-04-30T14:30:52",
  "models": {
    "gemini": {
      "model": "gemini-3-pro-image-preview",
      "temperature": 1.0,
      "aspect_ratio": "3:4",
      "resolution": "2K",
      "cost_per_image": 190
    },
    "gpt": {
      "model": "gpt-image-2",
      "quality": "high",
      "size": "1024x1536",
      "cost_per_image": 291
    }
  },
  "scenes": 6,
  "total_images": 12,
  "total_cost_estimate": 2886
}
```

---

## 비용 산정

| 모델 | 해상도 | 단가 | 6씬 x 2모델 |
|------|--------|------|------------|
| Gemini | 2K | ~190원 | 1,140원 |
| GPT Image 2 | high (1024x1536) | ~291원 | 1,746원 |
| **합계** | | | **~2,886원** |

---

## 백엔드 스크립트

| 스크립트 | 역할 |
|---------|------|
| `scripts/strategy_cut_builder/generate_duvetica_prompt_only.py` | 듀베티카 프롬프트 온리 생성 (검증 완료) |
| `scripts/strategy_cut_builder/generate_duvetica_dna_auto.py` | 듀베티카 DNA 자동 생성 |
| `scripts/strategy_cut_builder/generate_mlb_dna_auto.py` | MLB DNA 자동 생성 |
| `scripts/strategy_cut_builder/generate_mlb_dual.py` | MLB 듀얼(campaign+influencer) 생성 |
| `scripts/strategy_cut_builder/generate_mlb_discovery_parallel.py` | MLB+DISCOVERY 병렬 생성 |

---

## 금지 패턴

```python
# FORBIDDEN: 레퍼런스 이미지를 API 인풋으로
generate_image_to_pil(prompt, reference_images=[ref_img])

# FORBIDDEN: 순차 생성
for scene in scenes:
    gemini_img = generate_image_to_pil(scene["prompt"])
    time.sleep(5)
    gpt_img = generate_gpt_image(scene["prompt"])
    time.sleep(5)

# FORBIDDEN: 모델명 하드코딩
model = "gemini-3-pro-image-preview"  # core.config에서 import!

# FORBIDDEN: 가로형 비율
aspect_ratio = "16:9"  # 3:4 세로 고정!

# FORBIDDEN: GPT quality 미지정
generate_gpt_image(prompt)  # quality="high" 명시 필수
```

---

## 결과 표시 (output-rules.md 준수)

생성 완료 후 반드시 아래 형식으로 표시:

```
**[전략실컷 생성] 결과**

**브랜드**: DUVETICA / **유형**: Campaign / **시즌**: 26SS

**프롬프트**:
```
[실제 사용된 프롬프트 전문]
```

**설정**: 
- Gemini: temperature=1.0 / 비율=3:4 / 해상도=2K
- GPT: quality=high / size=1024x1536

**아웃풋**: Fnf_studio_outputs/strategy-cut-builder/duvetica/20260430_143052_campaign/
- scene_01_gemini.png / scene_01_gpt.png
- scene_02_gemini.png / scene_02_gpt.png
- ...

**비용**: ~2,886원 (12장)
```
