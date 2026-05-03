# WORKFLOW_BYPASS_OK: strategy-cut-builder DNA schema (2026-04-30)
"""DNA extraction JSON schemas — VLM fills these templates, never freeform.

These schemas match the existing preset format (db/presets/duvetica/*.json).
VLM gets the empty schema and fills in values. This guarantees preset-level detail.

Usage:
    from scripts.strategy_cut_builder.dna_schema import POSE_SCHEMA, EXPRESSION_SCHEMA, BACKGROUND_SCHEMA, PRODUCT_SCHEMA
"""

POSE_SCHEMA = {
    "summary": "(1줄 한국어 포즈 요약)",
    "stance": "(stand/sit/lean/walk/lie_back/recline/crouch)",
    "left_arm": {
        "description": "(왼팔 전체 위치/동작)",
        "hand": "(손이 뭘 하고 있는지 — 주머니, 턱 괴기, 가방 잡기, 폰 들기 등)",
        "elbow_angle": "(각도 — 예: 약 140도)",
        "elbow_direction": "(방향 — 바깥쪽/앞쪽/뒤쪽/위쪽)",
    },
    "right_arm": {
        "description": "(오른팔 전체 위치/동작)",
        "hand": "(손이 뭘 하고 있는지)",
        "elbow_angle": "(각도)",
        "elbow_direction": "(방향)",
    },
    "left_leg": {
        "description": "(왼다리 위치/동작)",
        "knee_angle": "(각도 — 서기=175도, 앉기=90도, 웅크리기=40도)",
        "knee_direction": "(무릎 방향 — 정면/왼쪽/오른쪽)",
        "knee_height": "(바닥/좌석/가슴 높이)",
        "foot_direction": "(발 방향)",
        "foot_position": "(바닥/교차/프레임 밖)",
    },
    "right_leg": {
        "description": "(오른다리 위치/동작)",
        "knee_angle": "(각도)",
        "knee_direction": "(방향)",
        "knee_height": "(높이)",
        "foot_direction": "(발 방향)",
        "foot_position": "(위치)",
    },
    "hip": {
        "description": "(엉덩이/무게중심 위치)",
        "torso_lean": "(상체 기울기 — 예: 뒤로 약 10도, 수직 등)",
    },
    "shoulder_line": "(어깨 비대칭/기울기 묘사)",
    "face_direction": "(정면/3/4왼쪽/3/4오른쪽/프로필/어깨너머)",
    "neck_tilt": "(목 기울기 — 예: 왼쪽으로 약 5도)",
    "head_angle": "(수평/살짝위/살짝아래)",
    "leg_shape": "(직립/교차/한다리올림/벌림/깊은스쿼트)",
    "camera": {
        "angle": "(정면/약간측면/프로필/뒤에서)",
        "height": "(눈높이/살짝하이앵글/살짝로앵글/탑뷰)",
        "framing": "(CU/MCU/MS/MFS/FS/LS)",
    },
}

EXPRESSION_SCHEMA = {
    "base": "(dreamy/serene/candid/confident/cool/neutral/playful)",
    "eyes": "(눈 상태 상세 — 반쯤감은, 크게뜬, 힘빠진, 직시, 내리깐 등 + 눈빛 묘사)",
    "gaze_direction": "(카메라/왼쪽/오른쪽/아래/위/먼곳/어깨너머)",
    "mouth": "(입 상태 상세 — 다문/살짝벌림/미소기운/입술긴장 등)",
    "face_angle": "(얼굴 회전 — 예: 정면에서 오른쪽 약 10도)",
    "chin": "(자연/살짝올림/살짝내림/손에기댐)",
    "note": "(이 표정의 맥락과 특이점 — 한국어 1~2문장)",
}

BACKGROUND_SCHEMA = {
    "type": "(장소 유형 — 카페앞/편의점/주차장/풀사이드/거리/계단 등)",
    "region_vibe": "(한국스트릿/지중해/유러피안/한강공원/실내카페/아웃도어 등)",
    "time_of_day": "(주간밝음/오후따뜻/골든아워/흐린날/야간/새벽 등)",
    "colors": "(배경 지배색 — 콘크리트그레이, 벽돌갈색, 녹색식물 등)",
    "setting_description": "(한국어 2~3문장 — 구체적 장소 묘사, 보이는 요소, 질감, 분위기)",
    "mood": "(전체 분위기 — minimalist premium/street cool/active energy 등)",
    "provided_elements": ["(배경이 제공하는 요소들 — 벽, 의자, 바닥, 간판, 차 등)"],
    "available_poses": ["(이 배경에서 가능한 자세들 — stand, sit, lean 등)"],
    "sit_surfaces": "(앉을 수 있는 곳 — 계단, 벤치, 차 후드, 없음)",
    "lighting_detail": "(광원 방향, 품질, 그림자 상세)",
    "notes": ["(특이사항 한국어)"],
}

PRODUCT_SCHEMA = {
    "garment_type": "(의류 유형 — crop tee, windbreaker, cargo pants 등)",
    "target_category": "(woven_jacket/setup/tee/pants/knit_polo/down/other)",
    "color_primary": "(주요 컬러)",
    "color_secondary": "(보조 컬러 또는 없음)",
    "fabric": "(1~5 — 1=천연프리미엄 2=천연혼방 3=중간 4=테크니컬 5=헤비테크)",
    "fit": "(1~5 — 1=스키니 2=슬림 3=레귤러 4=세미오버 5=오버사이즈)",
    "sheen": "(1~5 — 1=풀매트 2=소프트매트 3=세미 4=세미광택 5=하이광택)",
    "weight": "(1~5 — 1=초경량 2=경량 3=중간 4=중량 5=초중량)",
    "logo_visibility": "(없음/작게톤온톤/작게대비색/크게전면/올오버프린트)",
    "overall_mood": "(전체 분위기 한 줄)",
}

FULL_ANALYSIS_SCHEMA = {
    "image_type": "(product/marketing/graphic)",
    "product": PRODUCT_SCHEMA,
    "pose": POSE_SCHEMA,
    "expression": EXPRESSION_SCHEMA,
    "background": BACKGROUND_SCHEMA,
}


def get_vlm_prompt(schema: dict, context: str = "") -> str:
    """Build a VLM prompt that forces the model to fill the given JSON schema."""
    import json

    schema_str = json.dumps(schema, ensure_ascii=False, indent=2)

    return f"""이 이미지를 분석하고, 아래 JSON의 모든 괄호 안 설명을 실제 값으로 교체하세요.
빈 칸 없이 모든 필드를 채워야 합니다. 보이지 않는 부분은 "보이지않음"으로 적으세요.

{context}

아래 JSON을 복사하고 괄호 안 내용을 실제 분석 결과로 교체하세요:
```json
{schema_str}
```

JSON만 출력하세요. 설명, 마크다운, 추가 텍스트 금지."""


if __name__ == "__main__":
    import json
    import sys

    sys.stdout.reconfigure(encoding="utf-8")
    print("=== FULL ANALYSIS SCHEMA ===")
    print(json.dumps(FULL_ANALYSIS_SCHEMA, ensure_ascii=False, indent=2))
    print(f"\n=== VLM PROMPT EXAMPLE ===")
    print(get_vlm_prompt(POSE_SCHEMA, "포즈를 분석하세요.")[:500])
