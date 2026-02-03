from pathlib import Path
import re
import json

BASE_DIR = Path(__file__).resolve().parent
VALUES_FILE = BASE_DIR / "values.tsx.txt"

def load_ts_object(raw: str, name: str) -> dict:
    pattern = rf"{name}\s*=\s*({{[\s\S]*?}})"
    match = re.search(pattern, raw)
    if not match:
        raise ValueError(f"{name} не найден в values.tsx.txt")

    obj = match.group(1)
    obj = re.sub(r"(\w+):", r'"\1":', obj)
    obj = obj.replace("'", '"')
    return json.loads(obj)

def load_values():
    if not VALUES_FILE.exists():
        raise FileNotFoundError(
            f"❌ values.tsx.txt не найден. Ожидаемый путь: {VALUES_FILE}"
        )

    raw = VALUES_FILE.read_text(encoding="utf-8")

    return {
        "matrix": load_ts_object(raw, "MATRIX_VALUES"),
        "tasks": load_ts_object(raw, "TASKS")
    }
