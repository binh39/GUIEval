import pandas as pd
import numpy as np
import re
import json
import math
from collections import Counter, defaultdict
from pathlib import Path

class Config:    
    # ========== INPUT/OUTPUT ==========
    # Đường dẫn file dữ liệu gốc (Excel hoặc CSV)
    INPUT_PATH = r"E:\Code\LAB\split_leak\allAttriTrainEN.xlsx"
    
    # Thư mục lưu kết quả Step 1 (mapping nhóm)
    STEP1_OUTPUT_DIR = r"E:\Code\LAB\split_leak\step1_artifacts"
    
    # Thư mục lưu kết quả Step 2 (train/valid/test splits)
    STEP2_OUTPUT_DIR = r"E:\Code\LAB\split_leak\step2_splits"
    
    # ========== STEP 1: GOM CỤM ==========
    # Cột chứa text để gom cụm (None = tự động detect)
    # Ví dụ: "Sub Task" hoặc "Step Object" hoặc None
    EO_COL = "Sub Task"  
    
    # Tham số blocking (token hiếm)
    DF_CUT = 0.1           # Token có DF <= 10% được coi là "hiếm"
    RARE_TOKENS = 3        # Số token hiếm ghép thành blocking key
    MIN_TOKEN_LEN = 2      # Bỏ qua token có độ dài < 2
    
    # ========== STEP 2: CHIA TÁCH ==========
    # Chế độ gom nhóm:
    #   "subtask" -> gom cụm theo Sub Task
    #   "eo"      -> gom cụm theo Step Object (EO)
    #   "dual"    -> hợp nhất cả Sub Task lẫn Step Object
    GROUP_MODE = "subtask"
    
    # Tỉ lệ chia tập (phải tổng = 1.0)
    TRAIN_RATIO = 0.8
    VALID_RATIO = 0.0      # Đặt = 0 nếu chỉ muốn train/test
    TEST_RATIO = 0.2
    
    # Stratify theo các cột thuộc tính (giữ phân phối nhãn)
    # Ví dụ: ["ActionType", "ComponentType"] hoặc []
    STRATIFY_COLS = []
    
    # Random seed cho tái lập kết quả
    SEED = 42
tok_re = re.compile(r"[a-z0-9]+")

def normalize_text(s: str) -> str:
    """Chuẩn hóa text: lowercase, gộp khoảng trắng"""
    s = str(s).strip().lower()
    s = re.sub(r"\s+", " ", s)
    return s

def tokenize(s: str):
    """Tokenize text thành các từ (a-z0-9)"""
    return tok_re.findall(s)

def pick_text_col(df: pd.DataFrame, prefer_contains=("eo", "expected")) -> str:
    """
    Tự động chọn cột text tốt nhất dựa vào độ dài trung bình
    Ưu tiên các cột có tên chứa 'eo' hoặc 'expected'
    """
    obj_cols = [c for c in df.columns if df[c].dtype == "O"]
    if not obj_cols:
        return df.columns[0]
    preferred = [c for c in obj_cols if any(k in c.lower() for k in prefer_contains)]
    cols = preferred if preferred else obj_cols
    best, best_len = None, -1
    for c in cols:
        s = df[c].dropna().astype(str).map(len)
        L = float(s.mean()) if len(s) else 0.0
        if L > best_len:
            best, best_len = c, L
    return best

def build_block_keys(texts, df_cut=0.10, rare_topk=3, min_token_len=2):
    """
    Tạo blocking keys dựa trên token hiếm
    
    Args:
        texts: Danh sách text đã chuẩn hóa
        df_cut: Ngưỡng document frequency (0.1 = 10%)
        rare_topk: Số lượng token hiếm ghép thành key
        min_token_len: Độ dài tối thiểu của token
    
    Returns:
        keys: Danh sách blocking key cho mỗi text
        df_counts: Counter chứa document frequency của mỗi token
    """
    N = len(texts)
    df_counts = Counter()
    toks_per_row = []
    
    for t in texts:
        toks = tokenize(t)
        toks_per_row.append(toks)
        df_counts.update(set(toks))
    
    # Ngưỡng: token có DF <= common_cut được coi là "hiếm"
    common_cut = max(1, math.ceil(df_cut * N))
    
    keys = []
    uniq_id = 0
    
    for toks in toks_per_row:
        # Lọc token hiếm
        inf = [w for w in toks if len(w) >= min_token_len and df_counts[w] <= common_cut]
        
        if not inf:
            # Không có token hiếm -> key unique
            keys.append(f"__uniq__{uniq_id}")
            uniq_id += 1
        else:
            # Chọn top-k token hiếm nhất
            inf_sorted = sorted(inf, key=lambda w: (df_counts[w], w))[:rare_topk]
            keys.append("|".join(inf_sorted))
    
    return keys, df_counts

def groups_from_keys(keys):
    """Chuyển blocking keys thành groups (dict: key -> list of indices)"""
    groups = defaultdict(list)
    for i, k in enumerate(keys):
        groups[k].append(i)
    return groups


# ============================================================================
# 🔀 DISJOINT SET UNION (DSU) - CHO DUAL MODE (Cnay optional)
# ============================================================================
class DSU:
    """Disjoint Set Union với path compression"""
    def __init__(self, n):
        self.p = list(range(n))
        self.r = [0] * n
    
    def find(self, x):
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]  # path compression
            x = self.p[x]
        return x
    
    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return
        if self.r[ra] < self.r[rb]:
            self.p[ra] = rb
        elif self.r[ra] > self.r[rb]:
            self.p[rb] = ra
        else:
            self.p[rb] = ra
            self.r[ra] += 1


# ============================================================================
# 📊 CHIA TÁCH CLUSTER-EXCLUSIVE + STRATIFY
# ============================================================================

def group_split(indices_by_group, sizes, label_counts_by_group=None, target_label_hist=None):
    """
    Chia các nhóm vào train/valid/test sao cho:
    1. Cluster-exclusive: mỗi nhóm hoàn toàn thuộc 1 split
    2. Balanced size: gần với tỉ lệ mong muốn
    3. Stratified: giữ phân phối nhãn gần với global (nếu có)
    
    Args:
        indices_by_group: List[List[int]] - danh sách các nhóm
        sizes: Dict[str, int] - kích thước mong muốn cho mỗi split
        label_counts_by_group: List[Counter] - phân phối nhãn của từng nhóm
        target_label_hist: Counter - phân phối nhãn global mong muốn
    
    Returns:
        assign: Dict[int, str] - mapping group_index -> split_name
    """
    splits = list(sizes.keys())
    assign = {}
    cnt_size = {s: 0 for s in splits}
    cnt_label = {s: Counter() for s in splits}
    
    def capacity_score(s):
        """Còn bao nhiêu chỗ trống trong split s"""
        return sizes[s] - cnt_size[s]
    
    def label_cost_if_assign(s, g_idx):
        """Chi phí phân phối nhãn nếu gán nhóm g_idx vào split s"""
        if label_counts_by_group is None:
            return 0.0
        tmp = cnt_label[s].copy()
        tmp.update(label_counts_by_group[g_idx])
        denom = sum(tmp.values()) + 1e-9
        cost = 0.0
        for k, tgt in target_label_hist.items():
            cur = tmp[k] / denom
            cost += abs(cur - tgt)
        return cost
    
    # Ưu tiên gán các nhóm lớn trước (greedy)
    order = sorted(range(len(indices_by_group)), key=lambda i: -len(indices_by_group[i]))
    
    for g_idx in order:
        best_s, best_tuple = None, None
        for s in splits:
            cap = capacity_score(s)
            lcost = label_cost_if_assign(s, g_idx)
            score = (cap, -lcost)  # ưu tiên capacity cao, label cost thấp
            if (best_s is None) or (score > best_tuple):
                best_s, best_tuple = s, score
        
        assign[g_idx] = best_s
        cnt_size[best_s] += len(indices_by_group[g_idx])
        if label_counts_by_group is not None:
            cnt_label[best_s].update(label_counts_by_group[g_idx])
    
    return assign


# ============================================================================
# 📦 STEP 1: CHUẨN HÓA & GOM CỤM
# ============================================================================

def step1_normalize_and_group(config: Config):
    """
    Step 1: Đọc dữ liệu, chuẩn hóa, gom cụm theo blocking key
    
    Returns:
        df: DataFrame gốc
        eo_col: Tên cột được chọn
        groups: Dict[key -> list of indices]
        keys: List blocking keys
    """
    print("=" * 80)
    print("🚀 STEP 1: CHUẨN HÓA & GOM CỤM NGỮ NGHĨA")
    print("=" * 80)
    
    # 1. Đọc dữ liệu
    input_path = Path(config.INPUT_PATH)
    print(f"\n📂 Đang đọc dữ liệu từ: {input_path}")
    
    if input_path.suffix.lower() in [".xlsx", ".xls"]:
        df = pd.read_excel(input_path)
    else:
        df = pd.read_csv(input_path)
    
    print(f"✅ Đã đọc {len(df):,} dòng, {len(df.columns)} cột")
    
    # 2. Xác định cột text
    eo_col = config.EO_COL or pick_text_col(df)
    print(f"📝 Cột được chọn để gom cụm: '{eo_col}'")
    
    # 3. Chuẩn hóa text
    print(f"\n🔄 Đang chuẩn hóa text...")
    texts = df[eo_col].fillna("").map(normalize_text).tolist()
    
    # 4. Build blocking keys
    print(f"🔑 Đang tạo blocking keys (DF_CUT={config.DF_CUT}, RARE_TOKENS={config.RARE_TOKENS})...")
    keys, df_counts = build_block_keys(
        texts,
        df_cut=config.DF_CUT,
        rare_topk=config.RARE_TOKENS,
        min_token_len=config.MIN_TOKEN_LEN
    )
    
    # 5. Tạo groups
    groups = groups_from_keys(keys)
    num_groups = len(groups)
    sizes = sorted([len(v) for v in groups.values()], reverse=True)
    
    print(f"\n📊 Kết quả gom cụm:")
    print(f"   • Số nhóm: {num_groups:,}")
    print(f"   • Nhóm lớn nhất: {max(sizes):,} phần tử")
    print(f"   • Nhóm trung vị: {int(np.median(sizes))} phần tử")
    print(f"   • Số nhóm có ≥2 phần tử: {sum(1 for s in sizes if s >= 2):,}")
    
    # 6. Lưu mapping
    output_dir = Path(config.STEP1_OUTPUT_DIR)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    map_rows = []
    for k, idxs in groups.items():
        gsize = len(idxs)
        for i in idxs:
            map_rows.append({
                "row_index": int(i),
                "group_key": k,
                "group_size": int(gsize)
            })
    
    map_df = pd.DataFrame(map_rows).sort_values(
        ["group_size", "group_key", "row_index"],
        ascending=[False, True, True]
    )
    
    output_file = output_dir / "groups_blocking.csv"
    map_df.to_csv(output_file, index=False)
    print(f"\n💾 Đã lưu mapping tại: {output_file}")
    
    return df, eo_col, groups, keys


# ============================================================================
# 🔀 STEP 2: CHIA TÁCH CLUSTER-EXCLUSIVE
# ============================================================================

def step2_cluster_exclusive_split(df, groups, config: Config):
    """
    Step 2: Chia tách train/valid/test theo cluster-exclusive + stratify
    
    Args:
        df: DataFrame gốc
        groups: Dict[key -> list of indices] từ Step 1
        config: Đối tượng Config
    
    Returns:
        split: List[str] - nhãn split cho mỗi dòng
    """
    print("\n" + "=" * 80)
    print("🔀 STEP 2: CHIA TÁCH CLUSTER-EXCLUSIVE + STRATIFY")
    print("=" * 80)
    
    N = len(df)
    np.random.seed(config.SEED)
    
    # 1. Chuyển groups thành list
    groups_list = sorted(groups.values(), key=len, reverse=True)
    print(f"\n📊 Số nhóm: {len(groups_list):,}")
    
    # 2. Stratify (nếu có)
    label_counts_by_group = None
    target_label_hist = None
    
    if config.STRATIFY_COLS:
        print(f"📈 Stratify theo: {config.STRATIFY_COLS}")
        label_keys = (df[config.STRATIFY_COLS].astype(str).fillna("∅")).agg("|".join, axis=1).values
        global_hist = Counter(label_keys)
        total = sum(global_hist.values()) + 1e-9
        target_label_hist = Counter({k: v / total for k, v in global_hist.items()})
        
        label_counts_by_group = []
        for g in groups_list:
            cnt = Counter(label_keys[i] for i in g)
            label_counts_by_group.append(cnt)
    else:
        print("ℹ️  Không sử dụng stratify")
    
    # 3. Tính target sizes
    sizes = {
        "train": int(round(config.TRAIN_RATIO * N)),
        "valid": int(round(config.VALID_RATIO * N)),
        "test": int(round(config.TEST_RATIO * N))
    }
    sizes["train"] += (N - sum(sizes.values()))  # fix rounding residue
    
    print(f"\n🎯 Kích thước mong muốn:")
    for split_name, size in sizes.items():
        print(f"   • {split_name}: {size:,} ({size/N*100:.1f}%)")
    
    # 4. Gán nhóm vào split
    print(f"\n🔄 Đang gán nhóm vào các split...")
    assign = group_split(groups_list, sizes, label_counts_by_group, target_label_hist)
    
    split = [""] * N
    counts = {"train": 0, "valid": 0, "test": 0}
    
    for gi, g in enumerate(groups_list):
        sp = assign[gi]
        for i in g:
            split[i] = sp
        counts[sp] += len(g)
    
    print(f"\n✅ Kết quả thực tế:")
    for split_name, count in counts.items():
        print(f"   • {split_name}: {count:,} ({count/N*100:.1f}%)")
    
    return split


# ============================================================================
# 💾 LƯU KẾT QUẢ STEP 2
# ============================================================================

def save_splits(df, split, config: Config):
    """Lưu các split ra file XLSX (chỉ 2 cột: Sub Task, Step Object) và báo cáo JSON"""
    print("\n" + "=" * 80)
    print("💾 ĐANG LƯU KẾT QUẢ...")
    print("=" * 80)
    
    outdir = Path(config.STEP2_OUTPUT_DIR)
    outdir.mkdir(parents=True, exist_ok=True)
    
    df_out = df.copy()
    df_out["split"] = split
    
    # Kiểm tra cột tồn tại
    required_cols = ["Sub Task", "Step Object"]
    available_cols = [col for col in required_cols if col in df_out.columns]
    
    if not available_cols:
        print("⚠️  Cảnh báo: Không tìm thấy cột 'Sub Task' hoặc 'Step Object'")
        print(f"   Các cột có sẵn: {list(df_out.columns)}")
        available_cols = list(df_out.columns)[:2]  # Lấy 2 cột đầu tiên
        print(f"   Sử dụng các cột: {available_cols}")
    
    # Lưu từng split
    for split_name in ["train", "valid", "test"]:
        df_split = df_out[df_out["split"] == split_name]
        if len(df_split) > 0:
            # Chỉ lấy 2 cột cần thiết
            df_export = df_split[available_cols].copy()
            
            # Lưu ra file XLSX
            output_file = outdir / f"{split_name}.xlsx"
            df_export.to_excel(output_file, index=False, engine='openpyxl')
            print(f"✅ {split_name}.xlsx: {len(df_export):,} dòng, {len(available_cols)} cột ({', '.join(available_cols)})")
    
    # Lưu báo cáo
    report = {
        "input_file": str(config.INPUT_PATH),
        "total_rows": int(len(df)),
        "group_mode": config.GROUP_MODE,
        "stratify_cols": config.STRATIFY_COLS,
        "sizes_target": {
            "train": int(config.TRAIN_RATIO * len(df)),
            "valid": int(config.VALID_RATIO * len(df)),
            "test": int(config.TEST_RATIO * len(df))
        },
        "sizes_actual": {k: int(v) for k, v in Counter(split).items()},
        "step1_params": {
            "eo_col": config.EO_COL,
            "df_cut": config.DF_CUT,
            "rare_tokens": config.RARE_TOKENS,
            "min_token_len": config.MIN_TOKEN_LEN
        },
        "seed": config.SEED
    }
    
    report_file = outdir / "split_report.json"
    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    
    print(f"\n📄 Báo cáo: {report_file}")
    print(f"📁 Thư mục output: {outdir.absolute()}")


# ============================================================================
# 🚀 MAIN PIPELINE
# ============================================================================

def main():
    """Chạy toàn bộ pipeline"""
    print("\n" + "=" * 80)
    print("🎯 PIPELINE HOÀN CHỈNH: CHIA TÁCH DỮ LIỆU CHỐNG LEAK")
    print("=" * 80)
    print(f"📅 Thời gian: {pd.Timestamp.now()}")
    print("=" * 80)
    
    # Khởi tạo config
    config = Config()
    
    # Hiển thị config
    print("\n⚙️  CẤU HÌNH PIPELINE:")
    print(f"   📂 Input: {config.INPUT_PATH}")
    print(f"   📁 Step 1 output: {config.STEP1_OUTPUT_DIR}")
    print(f"   📁 Step 2 output: {config.STEP2_OUTPUT_DIR}")
    print(f"   📝 Cột gom cụm: {config.EO_COL or 'Auto-detect'}")
    print(f"   🔑 Blocking params: DF_CUT={config.DF_CUT}, RARE_TOKENS={config.RARE_TOKENS}")
    print(f"   📊 Tỉ lệ chia: train={config.TRAIN_RATIO}, valid={config.VALID_RATIO}, test={config.TEST_RATIO}")
    print(f"   🎲 Seed: {config.SEED}")
    
    try:
        # Step 1: Gom cụm
        df, eo_col, groups, keys = step1_normalize_and_group(config)
        
        # Step 2: Chia tách
        split = step2_cluster_exclusive_split(df, groups, config)
        
        # Lưu kết quả
        save_splits(df, split, config)
        
        print("\n" + "=" * 80)
        print("🎉 HOÀN THÀNH PIPELINE!")
        print("=" * 80)
        print(f"\n💡 Các file đã tạo:")
        print(f"   1. {config.STEP1_OUTPUT_DIR}/groups_blocking.csv")
        print(f"   2. {config.STEP2_OUTPUT_DIR}/train.xlsx")
        print(f"   3. {config.STEP2_OUTPUT_DIR}/valid.xlsx")
        print(f"   4. {config.STEP2_OUTPUT_DIR}/test.xlsx")
        print(f"   5. {config.STEP2_OUTPUT_DIR}/split_report.json")
        print(f"\n📝 Lưu ý: Các file XLSX chỉ chứa 2 cột: Sub Task, Step Object")
        
    except Exception as e:
        print(f"\n❌ LỖI: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
