"""Read the JSON object a model was asked to answer with.

Models wrap JSON in prose or code fences, leave // comments in it, or answer with a list of
objects; this tries those shapes in turn and raises ValueError when none parses.
"""

import json
import re


def parse_ai_json(content: str) -> dict:
    def strip_comments(json_str: str) -> str:
        json_str = re.sub(r"//[^\n]*", "", json_str)
        json_str = re.sub(r"/\*[\s\S]*?\*/", "", json_str)
        return json_str

    try:
        return json.loads(content.strip())
    except json.JSONDecodeError:
        pass

    try:
        return json.loads(strip_comments(content.strip()))
    except json.JSONDecodeError:
        pass

    json_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", content)
    if json_match:
        extracted = json_match.group(1)
        try:
            return json.loads(extracted)
        except json.JSONDecodeError:
            pass
        try:
            return json.loads(strip_comments(extracted))
        except json.JSONDecodeError:
            pass

    start_idx = content.find("{")
    if start_idx != -1:
        brace_count = 0
        for i, char in enumerate(content[start_idx:], start_idx):
            if char == "{":
                brace_count += 1
            elif char == "}":
                brace_count -= 1
                if brace_count == 0:
                    json_str = content[start_idx : i + 1]
                    try:
                        return json.loads(json_str)
                    except json.JSONDecodeError:
                        pass
                    try:
                        return json.loads(strip_comments(json_str))
                    except json.JSONDecodeError:
                        break

    start_idx = content.find("[")
    if start_idx != -1:
        bracket_count = 0
        for i, char in enumerate(content[start_idx:], start_idx):
            if char == "[":
                bracket_count += 1
            elif char == "]":
                bracket_count -= 1
                if bracket_count == 0:
                    json_str = content[start_idx : i + 1]
                    try:
                        result = json.loads(json_str)
                        if isinstance(result, list) and len(result) > 0:
                            if isinstance(result[0], dict):
                                return result[0]
                            return {"items": result}
                        return result
                    except json.JSONDecodeError:
                        break

    raise ValueError(f"Could not parse AI response as JSON: {content[:200]}")
