import pandas as pd
import os
import sys
if sys.version_info.major >= 3 and sys.version_info.minor >= 7:
    sys.stdout.reconfigure(encoding='utf-8')

def combine_excels_to_csv(excel_folder_path, output_csv_file):
    all_dataframes = []
    if not os.path.exists(excel_folder_path):
        print(f"Lỗi: Không tìm thấy thư mục '{excel_folder_path}'.")
        return
    for filename in os.listdir(excel_folder_path):
        if filename.endswith(('.xlsx', '.xls')):
            file_path = os.path.join(excel_folder_path, filename)    
            try:
                df = pd.read_excel(file_path, engine='openpyxl')
                columns_to_keep = ['Main Task', 'Sub Tasks', 'Steps']
                existing_columns = [col for col in columns_to_keep if col in df.columns]  
                if existing_columns:
                    filtered_df = df[existing_columns]
                    all_dataframes.append(filtered_df)
                    print(f"✅ Đã xử lý file: {filename}")
                else:
                    print(f"⚠️ Bỏ qua file '{filename}' vì không có các cột cần thiết.")
            except Exception as e:
                print(f"❌ Lỗi khi đọc file '{filename}': {e}")
    if all_dataframes:
        combined_df = pd.concat(all_dataframes, ignore_index=True)
        combined_df.to_csv(output_csv_file, index=False, encoding='utf-8-sig')
        print(f"\n🎉 Hoàn thành! Đã tổng hợp dữ liệu và lưu vào '{output_csv_file}'.")
    else:
        print("❌ Không có file Excel nào phù hợp để tổng hợp.")

excel_folder = 'DataExcel'  # Tên thư mục chứa Excel
output_csv = 'combined_tasks_en.csv' # Tên file CSV đầu ra
combine_excels_to_csv(excel_folder, output_csv)

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

# Step 3

csv_file_path = 'subtask_to_step_en.csv'
excel_file_path = 'subtask_and_step_en.xlsx'
columns_to_keep = ['Sub Task', 'Step Object']

# --- THỰC THI ---
try:
    print(f"Đang đọc file '{csv_file_path}'...")
    df = pd.read_csv(csv_file_path)
    df_selected = df[columns_to_keep]
    print(f"Đang ghi dữ liệu vào file '{excel_file_path}'...")
    df_selected.to_excel(excel_file_path, index=False)
    print("\nChuyển đổi thành công!")
    print(f"File kết quả đã được lưu tại: {excel_file_path}")
except FileNotFoundError:
    print(f"Lỗi: Không tìm thấy file '{csv_file_path}'. Vui lòng kiểm tra lại tên file và đảm bảo nó nằm cùng thư mục với script.")
except KeyError:
    print(f"Lỗi: Một hoặc nhiều cột trong {columns_to_keep} không có trong file CSV. Vui lòng kiểm tra lại tên cột.")
except Exception as e:
    print(f"Đã có lỗi xảy ra: {e}")