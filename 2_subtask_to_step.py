# Đọc /mnt/data/combined_tasks.csv, parse cột Sub Tasks (list[str]) và Steps (list[object]),
# rồi "explode" thành từng cặp Sub Task ↔ Step Object. Lưu ra /mnt/data/subtask_to_step.csv
# và liệt kê các dòng mismatch độ dài vào /mnt/data/mismatched_rows.csv

import pandas as pd
import json, ast
from pathlib import Path

src_path = Path("combined_tasks_en.csv")
out_pairs_path = Path("subtask_to_step_en.csv")
out_mismatch_path = Path("mismatched_rows.csv")

def parse_json_maybe(value):
    if pd.isna(value):
        return None
    if isinstance(value, (list, dict)):
        return value
    s = str(value).strip()
    if not s:
        return None
    for parser in (json.loads, ast.literal_eval):
        try:
            return parser(s)
        except Exception:
            continue
    return None

df = pd.read_csv(src_path)
df.rename(columns={c: c.strip().lower() for c in df.columns}, inplace=True)

# Xác định tên cột linh hoạt
def pick(cols, candidates):
    for c in candidates:
        if c in cols: return c
    return None

col_main  = pick(df.columns, ["main task", "main_task", "maintask"])
col_sub   = pick(df.columns, ["sub tasks", "sub task", "sub_tasks", "subtask", "subtasks"])
col_steps = pick(df.columns, ["steps", "step", "step objects", "step_object", "stepjson", "stepsjson"])
assert col_main and col_sub and col_steps, "Thiếu cột Main Task / Sub Tasks / Steps"

df["_sub_list"]   = df[col_sub].apply(parse_json_maybe)
df["_steps_list"] = df[col_steps].apply(parse_json_maybe)

pairs, mismatches = [], []
for idx, row in df.iterrows():
    subs, steps = row["_sub_list"], row["_steps_list"]
    if not isinstance(subs, list) or not isinstance(steps, list):
        mismatches.append({"row_index": idx, "reason": "Sub/Steps không phải list", "raw_sub": row[col_sub], "raw_steps": row[col_steps]})
        continue
    n = min(len(subs), len(steps))
    if len(subs) != len(steps):
        mismatches.append({"row_index": idx, "reason": f"len(subs)={len(subs)} != len(steps)={len(steps)}"})
    for i in range(n):
        sub_item = subs[i]
        step_item = steps[i]
        try:
            step_json_str = json.dumps(step_item, ensure_ascii=False, separators=(",", ":"))
        except Exception:
            step_json_str = json.dumps(ast.literal_eval(str(step_item)), ensure_ascii=False, separators=(",", ":"))
        pairs.append({
            "Main Task": row[col_main],
            "Sub Task": sub_item if isinstance(sub_item, str) else str(sub_item),
            "Step Object": step_json_str,
            "Row Index": idx,
            "Pair Index": i,
        })

pd.DataFrame(pairs).to_csv(out_pairs_path, index=False)
pd.DataFrame(mismatches).to_csv(out_mismatch_path, index=False)
