# データファイル設定
CONTROL_LIMIT_CALCULATION_FILE = "2025_TP15_モールド装置.csv"  # 管理限界計算用データ
ANOMALY_DETECTION_FILE = "テストデータ_202604.csv"  # 異常検知判定用データ

# Phase 2: 管理対象の特性値列名リスト
TARGET_COLUMNS = [
    "A剤流圧(Mpa)",
    "B剤流圧(Mpa)",
    "A剤タンク1圧力(Mpa)",
    "A剤タンク2圧力(Mpa)",
    "B剤タンク1圧力(Mpa)",
    "B剤タンク2圧力(Mpa)",
    "A剤配合比速度(Hz)",
    "B剤配合比速度(Hz)",
    "生産総合流速(％)",
    "生産吐出時間(sec)",
]

# d2係数テーブル（サンプルサイズ別）
# X-R管理図で範囲Rから標準偏差σを推定するための係数
D2_TABLE = {
    2: 1.128,
    3: 1.693,
    4: 2.059,
    5: 2.326,
    6: 2.534,
    7: 2.704,
    8: 2.847,
    9: 2.970,
    10: 3.078,
}

# 新JISルールの説明
JIS_RULES_DESCRIPTION = {
    1: "領域A超過点が1つ（管理限界超過）",
    2: "連続9点が中心線に対して同一側",
    3: "連続6点で単調増加または単調減少トレンド",
    4: "連続14点が交互に増減",
    5: "連続3点中2点以上が領域Aまたはそれを超えた領域（±2σ超過）",
    6: "連続5点中4点以上が領域Bまたはそれを超えた領域（±1σ超過）",
    7: "連続15点が領域C内（±1σ以内）",
    8: "連続8点が領域C超過（±1σ超過）",
}

# Phase 2: 管理図の画像ファイル出力設定
SAVE_FIGURES = (
    False  # デフォルトでグラフを出力しない（True: 出力する, False: 出力しない）
)

# Phase 2: 異常判定対象期間（日数）
DETECTION_DAYS = 7  # 直近N日間のみ異常判定を行う（最新7日間）

# Phase 2: グラフ表示期間（日数）
PLOT_DAYS = 30  # 管理図で表示する期間（最新30日間=約1ヶ月）

# Phase 3: AI異常検知用の特徴量エンジニアリング設定
def get_phase3_output_filename(input_filename, output_type):
    """
    入力ファイル名に基づいてPhase3の出力ファイル名を生成

    Parameters:
    -----------
    input_filename : str
        入力CSVファイル名（例: "2025_TP15_モールド装置.csv"）
    output_type : str
        出力タイプ（'features' または 'metadata'）

    Returns:
    --------
    str : 出力ファイル名
    """
    import os
    # ファイル名から拡張子を除去
    base_name = os.path.splitext(input_filename)[0]

    # 年度を判定してtrain/testを決定
    if '2025' in base_name:
        dataset_type = 'train'
    elif '2026' in base_name:
        dataset_type = 'test'
    else:
        # デフォルトでファイル名をそのまま使用
        dataset_type = base_name.replace('_', '-')

    # 出力ファイル名を生成
    if output_type == 'features':
        return f"{base_name}_features.csv"
    elif output_type == 'metadata':
        return f"{base_name}_features_metadata.json"
    else:
        raise ValueError(f"Unknown output_type: {output_type}")

# デフォルトのファイル名（互換性のために残す）
PHASE3_TRAIN_FEATURES_FILE = get_phase3_output_filename(CONTROL_LIMIT_CALCULATION_FILE, 'features')
PHASE3_TRAIN_METADATA_FILE = get_phase3_output_filename(CONTROL_LIMIT_CALCULATION_FILE, 'metadata')
PHASE3_TEST_FEATURES_FILE = get_phase3_output_filename(ANOMALY_DETECTION_FILE, 'features')
PHASE3_TEST_METADATA_FILE = get_phase3_output_filename(ANOMALY_DETECTION_FILE, 'metadata')

# Phase 1: 欠損IDファイル名
PHASE1_MISSING_IDS_JSON = "phase1_missing_ids.json"
PHASE1_MISSING_IDS_CSV = "phase1_missing_ids.csv"

# Phase 3: 日別データ件数集計ファイル名
PHASE3_DAILY_DATA_COUNTS_FILE = "phase3_daily_data_counts.json"

# Phase 3: 日付関連カラムの定義（データ内の形式を統一するため）
DATETIME_COLUMNS = [
    "投入開始日時",
    "取出終了日時",
    "余熱開始日時",
    "余熱終了日時",
    "注入開始日時",
    "注入終了日時",
    "硬化開始日時",
    "硬化終了日時",
    "生産日"
]

# Phase 3: ログファイル設定
PHASE3_LOG_DIR = "logs"
PHASE3_LOG_PREFIX = "phase3_feature_engineering"

# Phase 3: 実行モード設定
# 'train': モデル構築モード（学習・テスト両データを処理）
# 'predict': 予測モード（予測データのみを処理）
PHASE3_DEFAULT_MODE = "train"

# Phase 4: DataRobot予測設定
# サンプル予測データファイル（デフォルト入力）
PHASE4_SAMPLE_PREDICTIONS_FILE = "sample_predictions_data.csv"

# LLM分析データ出力ファイル（デフォルト出力）
PHASE4_LLM_ANALYSIS_FILE = "output/reports/phase4_llm_analysis_data.json"

# 生の予測結果CSVファイル出力先
PHASE4_RAW_PREDICTIONS_DIR = "output/reports"

# 予測説明の最大取得数
PHASE4_MAX_EXPLANATIONS = 10

# Feature Impact取得有効化（デフォルト）
PHASE4_FEATURE_IMPACT_ENABLED = True

# 非同期処理の使用（高速化）
PHASE4_USE_ASYNC = False

# Phase 4: ログファイル設定
PHASE4_LOG_DIR = "logs"
PHASE4_LOG_PREFIX = "phase4_datarobot_prediction"