#!/usr/bin/env python3
"""
PreToolUse Hook: brand-dna/*.json 작성 시 필수 키 검증

brand-dna/ 하위 JSON 파일을 Write/Edit할 때
필수 top-level 키와 가드레일 구조가 포함되어 있는지 검증한다.

필수 top-level 키:
  brand, season, positioning, mood, color, setting, styling, model, fabric, data_driven_guardrails

필수 guardrail 구조 (카테고리당):
  attributes (fabric/fit/sheen/weight with min/max/median), top_colors, garment_types
"""

import json
import sys
import re


def main():
    # stdin에서 hook 데이터 읽기
    try:
        hook_data = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, EOFError):
        # 파싱 실패 시 통과
        sys.exit(0)

    tool_name = hook_data.get("tool_name", "")
    tool_input = hook_data.get("tool_input", {})

    # Write 또는 Edit 도구인지 확인
    if tool_name not in ("Write", "Edit", "MultiEdit"):
        sys.exit(0)

    # 파일 경로 확인 — brand-dna/*.json 대상
    file_path = tool_input.get("file_path", "")
    if not file_path:
        sys.exit(0)

    # brand-dna/ 경로 + .json 파일만 대상
    if "brand-dna" not in file_path or not file_path.endswith(".json"):
        sys.exit(0)

    # schema.json은 검증 대상 아님
    if file_path.endswith("schema.json"):
        sys.exit(0)

    # Write인 경우 content에서 JSON 파싱 시도
    if tool_name == "Write":
        content = tool_input.get("content", "")
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            # JSON 파싱 실패 — 유효한 JSON이 아님
            print(
                "BLOCK: brand-dna JSON 파일의 내용이 유효한 JSON이 아닙니다.",
                file=sys.stderr,
            )
            sys.exit(2)

        # 필수 top-level 키 검증
        required_top_keys = [
            "brand",
            "season",
            "positioning",
            "mood",
            "color",
            "setting",
            "styling",
            "model",
            "fabric",
            "data_driven_guardrails",
        ]

        missing_top = [k for k in required_top_keys if k not in data]
        if missing_top:
            print(
                f"BLOCK: brand-dna JSON에 필수 top-level 키 누락: {', '.join(missing_top)}\n"
                f"필수 키: {', '.join(required_top_keys)}",
                file=sys.stderr,
            )
            sys.exit(2)

        # data_driven_guardrails 구조 검증
        guardrails = data.get("data_driven_guardrails", {})
        if not isinstance(guardrails, dict):
            print(
                "BLOCK: data_driven_guardrails는 dict여야 합니다.",
                file=sys.stderr,
            )
            sys.exit(2)

        if not guardrails:
            print(
                "BLOCK: data_driven_guardrails가 비어 있습니다. "
                "최소 1개 카테고리의 가드레일이 필요합니다.",
                file=sys.stderr,
            )
            sys.exit(2)

        # 각 카테고리별 필수 키 검증
        required_guardrail_keys = ["attributes", "top_colors", "garment_types"]
        required_attribute_keys = ["fabric", "fit", "sheen", "weight"]
        required_stat_keys = ["min", "max", "median"]

        errors = []
        for category, cat_data in guardrails.items():
            if not isinstance(cat_data, dict):
                errors.append(f"  [{category}] dict가 아닌 값")
                continue

            missing_cat = [k for k in required_guardrail_keys if k not in cat_data]
            if missing_cat:
                errors.append(f"  [{category}] 필수 키 누락: {', '.join(missing_cat)}")

            # attributes 내부 구조 검증
            attrs = cat_data.get("attributes", {})
            if isinstance(attrs, dict):
                for attr_name in required_attribute_keys:
                    if attr_name not in attrs:
                        errors.append(f"  [{category}].attributes.{attr_name} 누락")
                    elif isinstance(attrs[attr_name], dict):
                        missing_stat = [
                            s for s in required_stat_keys if s not in attrs[attr_name]
                        ]
                        if missing_stat:
                            errors.append(
                                f"  [{category}].attributes.{attr_name}: "
                                f"min/max/median 중 누락: {', '.join(missing_stat)}"
                            )

        if errors:
            error_msg = "\n".join(errors)
            print(
                f"BLOCK: data_driven_guardrails 구조 오류:\n{error_msg}\n\n"
                "각 카테고리에 필요한 구조:\n"
                '  {"attributes": {"fabric": {"min":N, "max":N, "median":N}, '
                '"fit": {...}, "sheen": {...}, "weight": {...}}, '
                '"top_colors": [...], "garment_types": [...]}',
                file=sys.stderr,
            )
            sys.exit(2)

    elif tool_name in ("Edit", "MultiEdit"):
        # Edit/MultiEdit는 부분 수정이므로 전체 구조 검증 불가
        # 필수 키를 삭제하는 패턴만 차단
        old_string = tool_input.get("old_string", "")
        new_string = tool_input.get("new_string", "")

        # data_driven_guardrails 키 자체를 삭제하려는 시도 차단
        if (
            "data_driven_guardrails" in old_string
            and "data_driven_guardrails" not in new_string
        ):
            print(
                "BLOCK: data_driven_guardrails 키를 삭제할 수 없습니다. "
                "이 키는 전략실컷빌더에 필수입니다.",
                file=sys.stderr,
            )
            sys.exit(2)

    # 검증 통과
    sys.exit(0)


if __name__ == "__main__":
    main()
