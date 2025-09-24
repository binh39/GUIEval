import pandas as pd
import sys
if sys.version_info.major >= 3 and sys.version_info.minor >= 7:
    sys.stdout.reconfigure(encoding='utf-8')

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