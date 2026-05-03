---
name: higgsfield
description: "Higgsfield MCP를 통한 이미지/영상 생성. 20개 모델(Soul, Flux, Seedream, GPT Image, Nano Banana 등) 지원. '힉스필드', 'higgsfield', '시네마틱 생성', 'soul 모델' 등의 요청에 반응합니다."
---

# Higgsfield MCP 이미지 생성

Higgsfield MCP를 통해 다양한 AI 이미지 모델로 이미지를 생성한다.

## MCP 연결 설정

### .mcp.json 설정

```json
{
  "higgsfield": {
    "command": "npx",
    "args": ["-y", "mcp-remote", "https://mcp.higgsfield.ai/mcp"]
  }
}
```

- 패키지: `mcp-remote` (npm)
- 인증: OAuth 방식 — 첫 연결 시 브라우저에서 Higgsfield 계정 로그인 필요
- 토큰 만료 시 재인증 필요 (`{"error":"Unauthorized"}` 발생하면 Claude Code 재시작)

### 트러블슈팅

| 증상 | 원인 | 해결 |
|------|------|------|
| `Failed to reconnect to higgsfield` | 패키지명 오류 또는 토큰 만료 | `.mcp.json`에서 `mcp-remote` 확인 + Claude Code 재시작 |
| `{"error":"Unauthorized"}` | OAuth 토큰 만료 | Claude Code 재시작 → 브라우저 로그인 |
| `npm error 404 @anthropic-ai/mcp-remote` | 잘못된 패키지명 | `mcp-remote`로 수정 (앞에 @anthropic-ai/ 붙이지 않음) |

## 계정 정보 확인

```
mcp__higgsfield__balance
→ { email, credits, subscription_plan_type }
```

## 이미지 모델 목록

### 패션/인플루언서 추천

| 모델 ID | 이름 | 제공사 | 특징 | 해상도 |
|---------|------|--------|------|--------|
| `soul_2` | Soul 2.0 | Higgsfield | 패션 에디토리얼, UGC, 캐릭터 | 1080p |
| `cinematic_studio_2_5` | Cinema Studio 2.5 | Higgsfield | 시네마틱 스틸, 고해상도 | 1K/2K/4K |
| `soul_cinematic` | Soul Cinema | Higgsfield | 시네마 컨셉아트 | - |
| `nano_banana_flash` | Nano Banana 2 | Google | 고퀄 포토리얼, 빠름 | 1K/2K/4K |
| `nano_banana_2` | Nano Banana Pro | Google | 최고 퀄리티 | 1K/2K/4K |
| `flux_2` | Flux 2.0 | Black Forest Labs | 프롬프트 정확도 최고 | 1K/2K |
| `seedream_v4_5` | Seedream 4.5 | Bytedance | 정밀 컨트롤, 4K | 4K |

### 기타 모델

| 모델 ID | 이름 | 제공사 | 특징 |
|---------|------|--------|------|
| `nano_banana` | Nano Banana | Google | 저렴, 리얼리스틱 |
| `gpt_image` | GPT Image 1.5 | OpenAI | 텍스트 렌더링 |
| `gpt_image_2` | GPT Image 2 | OpenAI | 4K, 포토리얼 |
| `grok_image` | Grok Imagine | xAI | 강렬한 대비 |
| `kling_omni_image` | Kling O1 Image | Kling | 포토리얼 |
| `flux_kontext` | Flux Kontext Max | Black Forest Labs | 스타일 트랜스퍼 |
| `seedream_v5_lite` | Seedream 5.0 lite | Bytedance | 인스트럭션 편집 |
| `z_image` | Z Image | Tongyi-MAI | 초고속, 스타일라이즈 |
| `marketing_studio_image` | Marketing Studio | Higgsfield | 제품 광고 |
| `soul_cast` | Soul Cast | Higgsfield | 캐릭터 일관성 |
| `soul_location` | Soul Location | Higgsfield | 환경/배경 생성 |
| `image_auto` | Auto | Higgsfield | 자동 모델 선택 |

### 모델 선택 가이드

| 용도 | 추천 모델 | 이유 |
|------|----------|------|
| 패션 에디토리얼 / 인플루언서 | `cinematic_studio_2_5` | 고해상도 + 시네마틱 품질 |
| UGC / 캔디드 감성 | `soul_2` | UGC 특화, 빠름 |
| 최고 퀄리티 (비용 무관) | `nano_banana_2` | Google 최고급 |
| 프롬프트 정확도 우선 | `flux_2` | 프롬프트 충실도 최고 |
| 빠른 테스트 | `nano_banana` 또는 `z_image` | 저렴 + 빠름 |
| 제품 광고/마케팅 | `marketing_studio_image` | 제품 연출 특화 |

## 생성 워크플로

### 1. 텍스트 프롬프트만으로 생성 (prompt-only)

```
mcp__higgsfield__generate_image({
  params: {
    model: "cinematic_studio_2_5",
    prompt: "프롬프트 텍스트",
    aspect_ratio: "3:4",
    resolution: "2k",
    count: 1
  }
})
```

### 2. 레퍼런스 이미지 포함 생성

```
# Step 1: 이미지 업로드
mcp__higgsfield__media_upload({ filename: "ref.jpg", content_type: "image/jpeg" })
# → presigned URL 반환 → curl PUT 실행
mcp__higgsfield__media_confirm(...)

# Step 2: 업로드된 미디어 ID로 생성
mcp__higgsfield__generate_image({
  params: {
    model: "soul_2",
    prompt: "프롬프트",
    aspect_ratio: "3:4",
    medias: [{ value: "미디어UUID", role: "image" }]
  }
})
```

### 3. 결과 확인

```
# 동기 대기 (최대 ~25초)
mcp__higgsfield__job_status({ jobId: "UUID", sync: true })
# → status: "completed" → results.rawUrl 에서 이미지 다운로드

# 비동기 폴링
mcp__higgsfield__job_status({ jobId: "UUID" })
# → poll_after_seconds 후 재호출
```

### 4. 이미지 다운로드 + 저장

```python
import requests
from pathlib import Path

url = "https://d8j0ntlcm91z4.cloudfront.net/user_.../hf_*.png"
out = Path("Fnf_studio_outputs/strategy-cut-builder/...")
out.mkdir(parents=True, exist_ok=True)

r = requests.get(url, timeout=60)
(out / "result_higgsfield.png").write_bytes(r.content)
```

## 비용

- 크레딧 기반 (자동 충전 아님, 수동 구매)
- `mcp__higgsfield__balance` 로 잔여 크레딧 확인
- `mcp__higgsfield__transactions` 로 사용 내역 확인
- 충전: https://higgsfield.ai/pricing

## 기존 파이프라인과 연동

전략컷빌더 등 기존 프롬프트 파이프라인(DNA → 속성 → 프롬프트)의 결과물을 그대로 Higgsfield에 전달 가능:

```
attribute_to_prompt.py → 프롬프트 텍스트
    ↓
mcp__higgsfield__generate_image(prompt=프롬프트)
    ↓
job_status(sync=true) → rawUrl
    ↓
다운로드 → Fnf_studio_outputs/
```

Gemini/GPT와 동일 프롬프트로 생성하여 모델 간 비교 가능.

## 주의사항

- 2K/4K 해상도 이미지는 파일 크기가 10MB+ — curl 다운로드 타임아웃 가능, Python requests 사용 권장
- `soul_2`는 1080p 고정 (768x1024) — 고해상도 필요 시 `cinematic_studio_2_5` 또는 `nano_banana_2` 사용
- 모델별 지원 aspect_ratio가 다름 — `models_explore(action="get", model_id="...")` 로 확인
