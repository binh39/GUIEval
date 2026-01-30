import pandas as pd
import json
from collections import Counter

# Hàm parse JSON an toàn (từ code trước đó)
def safe_json_parse(text: str):
    if not isinstance(text, str):
        return None, False
    try:
        return json.loads(text), True
    except json.JSONDecodeError:
        # fallback: cố sửa ngoặc thừa thiếu
        fixed = text
        # đảm bảo số { == }
        while fixed.count("{") > fixed.count("}"):
            fixed += "}"
        while fixed.count("{") < fixed.count("}"):
            fixed = "{" + fixed
        try:
            return json.loads(fixed), True
        except:
            return None, False
    return None, False

# Định nghĩa map category CSS (có thể thêm các thuộc tính khác sau)
CSS_CATEGORY_MAP = {
    "font-size": "Font",
    "font-family": "Font",
    "font-weight": "Font",
    "font-style": "Font",
    "line-height": "Font",
    "text-decoration": "Font",
    "text-transform": "Font",
    "text-align": "Font",
    
    "color": "Color & Background",
    "background-color": "Color & Background",
    "background-image": "Color & Background",
    "background-size": "Color & Background",
    "background-position": "Color & Background",
    "background-repeat": "Color & Background",
    "opacity": "Color & Background",
    "fill": "Color & Background",
    "stroke": "Color & Background",
    
    "border": "Border",
    "border-width": "Border",
    "border-style": "Border",
    "border-color": "Border",
    "border-radius": "Border",
    "border-top": "Border",
    "border-right": "Border",
    "border-bottom": "Border",
    "border-left": "Border",
    "border-top-width": "Border",
    "border-right-width": "Border",
    "border-bottom-width": "Border",
    "border-left-width": "Border",
    "border-top-style": "Border",
    "border-right-style": "Border",
    "border-bottom-style": "Border",
    "border-left-style": "Border",
    "border-top-color": "Border",
    "border-right-color": "Border",
    "border-bottom-color": "Border",
    "border-left-color": "Border",
    "outline": "Border",

    
    "width": "Layout & Size",
    "height": "Layout & Size",
    "min-width": "Layout & Size",
    "max-width": "Layout & Size",
    "min-height": "Layout & Size",
    "max-height": "Layout & Size",
    "display": "Layout & Size",
    "position": "Layout & Size",
    "top": "Layout & Size",
    "right": "Layout & Size",
    "bottom": "Layout & Size",
    "left": "Layout & Size",
    "float": "Layout & Size",
    "clear": "Layout & Size",
    "z-index": "Layout & Size",
    "overflow": "Layout & Size",
    "overflow-x": "Layout & Size",
    "overflow-y": "Layout & Size",
    "x": "Layout & Size",
    "y": "Layout & Size",
    "rendered-width": "Layout & Size",
    "rendered-height": "Layout & Size",
    "natural-width": "Layout & Size",
    "natural-height": "Layout & Size",
    "column-gap": "Layout & Size",
    "row-gap": "Layout & Size",
    "box-shadow": "Layout & Size",
    "box-sizing": "Layout & Size",
    
    "margin": "Spacing",
    "margin-top": "Spacing",
    "margin-right": "Spacing",
    "margin-bottom": "Spacing",
    "margin-left": "Spacing",
    "padding": "Spacing",
    "padding-top": "Spacing",
    "padding-right": "Spacing",
    "padding-bottom": "Spacing",
    "padding-left": "Spacing",

    "text-content": "Content",
    "placeholder": "Content",
    "alt-text": "Content",
    "title": "Content",
    "aria-label": "Content",
    "line-break": "Content",

    "transform": "Transform & Animation",
    "transition": "Transform & Animation",
    "transition-duration": "Transform & Animation",
    "animation": "Transform & Animation",
    "animation-duration": "Transform & Animation",
    "transform-style": "Transform & Animation",
    "scale": "Transform & Animation",
    "rotate": "Transform & Animation",
    "translate": "Transform & Animation",
    "offset": "Transform & Animation",
    "offset-path": "Transform & Animation",
    "offset-distance": "Transform & Animation",
    "offset-rotate": "Transform & Animation",

    "clicked": "Interaction & State",
    "hovered": "Interaction & State",
    "focused": "Interaction & State",
    "enabled": "Interaction & State",
    "active": "Interaction & State",
    "visibility": "Interaction & State",
    "id": "Interaction & State",
    "url": "Interaction & State",
    "src": "Interaction & State",
    "value": "Interaction & State",
    "count": "Interaction & State",
    "cursor": "Interaction & State",
}

def analyze_css_property_frequency(file_path):
    try:
        # Nếu file là .xlsx dùng read_excel, hỗ trợ .csv dùng read_csv
        if str(file_path).lower().endswith((".xls", ".xlsx", ".xlsm", ".xlsb")):
            df = pd.read_excel(file_path)
        else:
            df = pd.read_csv(file_path)
    except FileNotFoundError:
        return f"Lỗi: Không tìm thấy file '{file_path}'.", None, None, None
    except Exception as e:
        # In traceback để dễ debug trong terminal
        import traceback
        traceback.print_exc()
        return f"Lỗi khi đọc file '{file_path}': {e}", None, None, None

    all_keys = []
    
    # Giả định cột chứa JSON đầu vào/ground truth là "Step Object"
    for _, row in df.iterrows():
        json_str = row.get("Step Object")
        
        parsed_json, is_valid = safe_json_parse(json_str)
        
        if is_valid and isinstance(parsed_json, dict):
            # Lấy đối tượng "expected"
            expected = parsed_json.get("expected")
            
            if isinstance(expected, dict):
                # Thêm tất cả các key trong expected vào danh sách
                all_keys.extend(expected.keys())
    
    # 1. Đếm tần suất cá nhân
    key_counts = Counter(all_keys)
    total_samples = df.shape[0] # Tổng số mẫu là tổng số dòng
    total_properties = len(all_keys) # Tổng số thuộc tính được tìm thấy (có thể lớn hơn total_samples)
    
    # 2. Đếm tần suất Category
    category_counts = Counter()
    
    for key, count in key_counts.items():
        category = CSS_CATEGORY_MAP.get(key, "Uncategorized")
        category_counts[category] += count

    # Tạo DataFrame kết quả
    
    # Kết quả Category
    category_results = []
    for category, count in category_counts.most_common():
        percentage_of_properties = (count / total_properties) * 100 if total_properties > 0 else 0
        category_results.append({
            "Category": category,
            "Count": count,
            "Percentage_of_Total_Properties": f"{percentage_of_properties:.2f}%"
        })
    df_category = pd.DataFrame(category_results)
    
    # Kết quả Individual Key
    key_results = []
    for key, count in key_counts.most_common():
        category = CSS_CATEGORY_MAP.get(key, "Uncategorized")
        percentage_of_properties = (count / total_properties) * 100 if total_properties > 0 else 0
        key_results.append({
            "Key": key,
            "Category": category,
            "Count": count,
            "Percentage_of_Total_Properties": f"{percentage_of_properties:.2f}%"
        })
    df_key = pd.DataFrame(key_results)
    
    # Lưu kết quả
    output_path = "css_frequency_analysis.xlsx"
    try:
        with pd.ExcelWriter(output_path) as writer:
            df_category.to_excel(writer, sheet_name="Category Frequency", index=False)
            df_key.to_excel(writer, sheet_name="Key Frequency", index=False)
    except ImportError as ie:
        # Thường thiếu openpyxl khi ghi Excel
        print("Lỗi khi ghi file Excel:", ie)
        print("Hãy cài `openpyxl`: python -m pip install openpyxl")
        return df_category, total_samples, total_properties, None
    except Exception:
        import traceback
        traceback.print_exc()
        return f"Lỗi khi ghi file '{output_path}'", total_samples, total_properties, None
        
    return df_category, total_samples, total_properties, output_path

file_name = "data.xlsx"
print("Bắt đầu phân tích tần suất thuộc tính CSS...")
results = analyze_css_property_frequency(file_name)

if isinstance(results[0], pd.DataFrame):
    df_category, total_samples, total_properties, output_file = results
    
    print(f"Tổng số mẫu (rows) đã phân tích: {total_samples}")
    print(f"Tổng số thuộc tính CSS được tìm thấy: {total_properties}")
    print(f"Kết quả đã được lưu vào file: {output_file}")
    
    print("\n--- Tần suất Xuất hiện theo Nhóm (Top 10) ---")
    print(df_category.head(10).to_markdown(index=False))
else:
    print(results[0]) # In thông báo lỗi nếu không tìm thấy file