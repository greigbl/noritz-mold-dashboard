#!/usr/bin/env python3
"""
Phase 3: AI異常検知のための特徴量エンジニアリング

モールド装置データに対して特徴量エンジニアリングを実施し、
DataRobotでのAI異常検知モデル構築に使用する。

主な機能:
- 日付形式の統一処理（Excel形式、文字列形式に対応）
- 物理法則ベースの特徴量生成
- ドメイン知識に基づく品質指標
- 行単位で計算可能な特徴量のみを実装
- ログ出力機能
"""

import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta
import json
import warnings
import logging
import sys
from app.manufacturing.pipeline import config

warnings.filterwarnings('ignore')


class MoldFeatureEngineering:
    """モールド装置データの特徴量エンジニアリングクラス"""

    def __init__(self, data_path, feature_mode=None, log_to_file=True):
        """
        初期化

        Parameters:
        -----------
        data_path : str or Path
            入力CSVファイルのパス
        feature_mode : str, optional
            特徴量生成モード ('full' or 'top25')
            Noneの場合はconfig.PHASE3_FEATURE_MODEを使用
        log_to_file : bool
            ログをファイルに出力するか（デフォルト: True）
        """
        self.data_path = Path(data_path)
        self.df = None
        self.feature_mode = feature_mode if feature_mode is not None else config.PHASE3_FEATURE_MODE
        self.feature_metadata = {
            'created_at': datetime.now().strftime('%Y%m%d_%H%M%S'),
            'input_file': str(self.data_path),
            'feature_mode': self.feature_mode,
            'original_columns': [],
            'features': {}
        }

        # ログの設定
        self.setup_logging(log_to_file)

    def setup_logging(self, log_to_file):
        """ログ設定"""
        self.logger = logging.getLogger(f'phase3_{self.data_path.stem}')
        self.logger.setLevel(logging.INFO)

        # 既存のハンドラをクリア
        self.logger.handlers = []

        # コンソールハンドラ
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_formatter = logging.Formatter('%(message)s')
        console_handler.setFormatter(console_formatter)
        self.logger.addHandler(console_handler)

        # ファイルハンドラ（オプション）
        if log_to_file:
            log_dir = Path(config.PHASE3_LOG_DIR)
            log_dir.mkdir(exist_ok=True)

            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            log_file = log_dir / f"{config.PHASE3_LOG_PREFIX}_{self.data_path.stem}_{timestamp}.log"

            file_handler = logging.FileHandler(log_file, encoding='utf-8')
            file_handler.setLevel(logging.DEBUG)
            file_formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            file_handler.setFormatter(file_formatter)
            self.logger.addHandler(file_handler)

            self.logger.info(f"ログファイル: {log_file}")

    def load_data(self):
        """データの読み込み"""
        self.logger.info("\n=== データ読み込み ===")
        self.logger.info(f"入力ファイル: {self.data_path}")

        # エンコーディングの自動判定
        for encoding in ['shift-jis', 'cp932', 'utf-8-sig', 'utf-8']:
            try:
                self.df = pd.read_csv(self.data_path, encoding=encoding)
                self.logger.info(f"エンコーディング: {encoding}")
                break
            except UnicodeDecodeError:
                continue

        if self.df is None:
            raise ValueError(f"ファイルを読み込めませんでした: {self.data_path}")

        self.logger.info(f"読み込み完了: {len(self.df):,}行 × {len(self.df.columns)}列")

        # メタデータに元のカラムを記録
        self.feature_metadata['original_columns'] = list(self.df.columns)
        self.feature_metadata['original_rows'] = len(self.df)

        return self

    def standardize_datetime_columns(self):
        """日時カラムのデータ形式を統一"""
        self.logger.info("\n=== 日時データの形式統一 ===")

        for col in config.DATETIME_COLUMNS:
            if col not in self.df.columns:
                continue

            self.logger.debug(f"処理中: {col}")

            # 変換前のサンプル値を記録
            sample_values = self.df[col].dropna().head(3).tolist()
            self.logger.debug(f"  変換前サンプル: {sample_values}")

            # 日時形式を統一
            self.df[col] = self.df[col].apply(self._convert_to_datetime)

            # 変換後のサンプル値を記録
            converted_samples = self.df[col].dropna().head(3).tolist()
            self.logger.debug(f"  変換後サンプル: {converted_samples}")

            # 変換成功率を記録
            null_count = self.df[col].isna().sum()
            success_rate = (len(self.df) - null_count) / len(self.df) * 100
            self.logger.info(f"  {col}: 変換成功率 {success_rate:.1f}% (欠損: {null_count}件)")

        return self

    def _convert_to_datetime(self, value):
        """
        様々な形式の日時データを統一形式（float型のExcel形式）に変換

        Parameters:
        -----------
        value : various
            日時データ（Excel数値、文字列、datetime等）

        Returns:
        --------
        float : Excel形式の日時（1900年1月1日からの日数）
        """
        if pd.isna(value):
            return np.nan

        # 既にfloat/int型（Excel形式）の場合はそのまま返す
        if isinstance(value, (int, float)):
            return float(value)

        # datetime型の場合
        if isinstance(value, (datetime, pd.Timestamp)):
            # Excel形式に変換（1900年1月1日を基準）
            excel_base = datetime(1899, 12, 30)
            delta = value - excel_base
            return delta.total_seconds() / 86400

        # 文字列の場合
        if isinstance(value, str):
            try:
                # 複数の日付形式を試行
                for fmt in [
                    '%Y/%m/%d %H:%M:%S',
                    '%Y-%m-%d %H:%M:%S',
                    '%Y/%m/%d %H:%M',
                    '%Y-%m-%d %H:%M',
                    '%Y/%m/%d',
                    '%Y-%m-%d',
                    '%Y年%m月%d日',
                    '%m/%d/%Y',
                    '%d/%m/%Y'
                ]:
                    try:
                        dt = datetime.strptime(value.strip(), fmt)
                        excel_base = datetime(1899, 12, 30)
                        delta = dt - excel_base
                        return delta.total_seconds() / 86400
                    except:
                        continue

                # pandas.to_datetimeで試行
                dt = pd.to_datetime(value)
                excel_base = datetime(1899, 12, 30)
                delta = dt - pd.Timestamp(excel_base)
                return delta.total_seconds() / 86400

            except:
                return np.nan

        return np.nan

    def create_time_features(self):
        """時間特徴量の生成"""
        self.logger.info("\n=== 時間特徴量の生成 ===")

        created_features = 0
        # 日時カラムから時間成分を抽出
        for col in config.DATETIME_COLUMNS:
            if col not in self.df.columns:
                continue

            # Excel形式の日時から時間成分を抽出
            if not self.df[col].isna().all():
                # pandasのdatetimeに一時的に変換して成分を抽出
                temp_datetime = pd.to_datetime('1899-12-30') + pd.to_timedelta(self.df[col], unit='D')

                # NaNを含む場合はInt64（nullable integer）を使用
                self.df[f'{col}_hour'] = temp_datetime.dt.hour.astype('Int64')
                self.df[f'{col}_dayofweek'] = temp_datetime.dt.dayofweek.astype('Int64')
                self.df[f'{col}_day'] = temp_datetime.dt.day.astype('Int64')
                self.df[f'{col}_month'] = temp_datetime.dt.month.astype('Int64')

                self.feature_metadata['features'][f'{col}_hour'] = f'{col}の時間'
                self.feature_metadata['features'][f'{col}_dayofweek'] = f'{col}の曜日'
                self.feature_metadata['features'][f'{col}_day'] = f'{col}の日'
                self.feature_metadata['features'][f'{col}_month'] = f'{col}の月'

                created_features += 4

        self.logger.info(f"  生成した時間成分特徴量: {created_features}個")
        return self

    def create_process_time_features(self):
        """プロセス時間関連の特徴量生成"""
        self.logger.info("\n=== プロセス時間特徴量の生成 ===")

        # 工程実行時間の計算（分単位）
        process_pairs = [
            ('余熱開始日時', '余熱終了日時', 'preheat_duration'),
            ('注入開始日時', '注入終了日時', 'injection_duration'),
            ('硬化開始日時', '硬化終了日時', 'curing_duration'),
            ('投入開始日時', '取出終了日時', 'total_cycle_time')
        ]

        for start_col, end_col, feature_name in process_pairs:
            if start_col in self.df.columns and end_col in self.df.columns:
                # Excel形式の日数差を分に変換
                self.df[feature_name] = (self.df[end_col] - self.df[start_col]) * 24 * 60
                self.feature_metadata['features'][feature_name] = f'{feature_name}（分）'

                # 負の時間（異常値）フラグ
                self.df[f'{feature_name}_negative'] = (self.df[feature_name] < 0).astype(int)
                self.feature_metadata['features'][f'{feature_name}_negative'] = f'{feature_name}の負値フラグ'

        # 工程間の待機時間
        if '余熱終了日時' in self.df.columns and '注入開始日時' in self.df.columns:
            self.df['wait_preheat_to_injection'] = (
                self.df['注入開始日時'] - self.df['余熱終了日時']
            ) * 24 * 60
            self.feature_metadata['features']['wait_preheat_to_injection'] = '余熱から注入までの待機時間（分）'

        if '注入終了日時' in self.df.columns and '硬化開始日時' in self.df.columns:
            self.df['wait_injection_to_curing'] = (
                self.df['硬化開始日時'] - self.df['注入終了日時']
            ) * 24 * 60
            self.feature_metadata['features']['wait_injection_to_curing'] = '注入から硬化までの待機時間（分）'

        # 各工程の時間比率
        if 'total_cycle_time' in self.df.columns and self.df['total_cycle_time'].sum() > 0:
            for feature_name in ['preheat_duration', 'injection_duration', 'curing_duration']:
                if feature_name in self.df.columns:
                    self.df[f'{feature_name}_ratio'] = (
                        self.df[feature_name] / (self.df['total_cycle_time'] + 1e-10)
                    )
                    self.feature_metadata['features'][f'{feature_name}_ratio'] = f'{feature_name}の時間比率'

        # 工程時間の相対比率
        duration_cols = ['preheat_duration', 'injection_duration', 'curing_duration']
        existing_durations = [col for col in duration_cols if col in self.df.columns]

        if len(existing_durations) >= 2:
            for i in range(len(existing_durations)):
                for j in range(i+1, len(existing_durations)):
                    col1, col2 = existing_durations[i], existing_durations[j]
                    feature_name = f'{col1}_{col2}_ratio'
                    self.df[feature_name] = self.df[col1] / (self.df[col2] + 1e-10)
                    self.feature_metadata['features'][feature_name] = f'{col1}と{col2}の比率'

        self.logger.info(f"  生成した時間特徴量: {len([k for k in self.feature_metadata['features'] if 'duration' in k or 'wait' in k])}個")

        return self

    def create_physical_features(self):
        """物理法則ベースの特徴量生成"""
        self.logger.info("\n=== 物理法則ベース特徴量の生成 ===")

        # 材料バランス検証
        if all(col in self.df.columns for col in ['A剤配合比速度', 'B剤配合比速度', '生産吐出時間']):
            expected_ratio = 1.0  # 理想的な配合比
            self.df['material_balance_error'] = abs(
                (self.df['A剤配合比速度'] * self.df['生産吐出時間']) -
                (self.df['B剤配合比速度'] * self.df['生産吐出時間'] * expected_ratio)
            )
            self.feature_metadata['features']['material_balance_error'] = '材料バランス誤差'

        # エネルギーバランス
        if all(col in self.df.columns for col in ['A剤流圧_Mpa', 'B剤流圧_Mpa', 'A剤配合比速度', 'B剤配合比速度', '生産吐出時間']):
            self.df['energy_balance'] = (
                self.df['A剤流圧_Mpa'] * self.df['A剤配合比速度'] +
                self.df['B剤流圧_Mpa'] * self.df['B剤配合比速度']
            ) * self.df['生産吐出時間']
            self.feature_metadata['features']['energy_balance'] = 'エネルギーバランス'

        # 圧力と流速の物理的関係
        if '生産総合流速' in self.df.columns:
            for agent in ['A剤', 'B剤']:
                pressure_col = f'{agent}流圧_Mpa'
                if pressure_col in self.df.columns:
                    # 圧力×流速（仕事率的な指標）
                    self.df[f'{agent}_power'] = self.df[pressure_col] * self.df['生産総合流速']
                    self.feature_metadata['features'][f'{agent}_power'] = f'{agent}の仕事率指標'

                    # 圧力/流速（抵抗的な指標）
                    self.df[f'{agent}_resistance'] = self.df[pressure_col] / (self.df['生産総合流速'] + 1e-10)
                    self.feature_metadata['features'][f'{agent}_resistance'] = f'{agent}の抵抗指標'

        self.logger.info(f"  生成した物理法則特徴量: {len([k for k in self.feature_metadata['features'] if 'balance' in k or 'power' in k or 'resistance' in k])}個")

        return self

    def create_quality_features(self):
        """品質予測スコアの生成"""
        self.logger.info("\n=== 品質予測スコアの生成 ===")

        # 圧力安定性スコア
        pressure_cols = ['A剤流圧_Mpa', 'B剤流圧_Mpa']
        if all(col in self.df.columns for col in pressure_cols):
            self.df['pressure_stability_score'] = 1 / (
                self.df[pressure_cols].std(axis=1) + 1e-10
            )
            self.feature_metadata['features']['pressure_stability_score'] = '圧力安定性スコア'

        # 配合精度スコア
        if 'A剤配合比速度' in self.df.columns and 'B剤配合比速度' in self.df.columns:
            self.df['mix_ratio'] = self.df['A剤配合比速度'] / (self.df['B剤配合比速度'] + 1e-10)
            self.df['mixing_precision_score'] = 1 / (
                abs(self.df['mix_ratio'] - 1.0) + 1e-10
            )
            self.feature_metadata['features']['mix_ratio'] = 'A剤とB剤の配合比率'
            self.feature_metadata['features']['mixing_precision_score'] = '配合精度スコア'

        # プロセス効率スコア
        if '生産吐出時間' in self.df.columns and 'total_cycle_time' in self.df.columns:
            self.df['process_efficiency_score'] = (
                self.df['生産吐出時間'] / (self.df['total_cycle_time'] + 1e-10)
            )
            self.feature_metadata['features']['process_efficiency_score'] = 'プロセス効率スコア'

        self.logger.info(f"  生成した品質スコア: {len([k for k in self.feature_metadata['features'] if 'score' in k])}個")

        return self

    def create_entropy_features(self):
        """エントロピーベースの特徴量生成"""
        self.logger.info("\n=== エントロピー特徴量の生成 ===")

        # センサー値のエントロピー（行内のばらつき）
        sensor_cols = [col for col in self.df.columns if 'Mpa' in col or '速度' in col or '流速' in col]

        if len(sensor_cols) >= 2:
            def calculate_row_entropy(row):
                """行内のセンサー値のエントロピーを計算"""
                values = row[sensor_cols].dropna().values
                if len(values) == 0:
                    return 0

                # ヒストグラムでビンに分割
                hist, _ = np.histogram(values, bins=10)
                hist = hist[hist > 0]  # ゼロを除外
                if len(hist) == 0:
                    return 0

                # エントロピー計算
                prob = hist / hist.sum()
                entropy = -np.sum(prob * np.log(prob + 1e-10))
                return entropy

            self.df['sensor_entropy'] = self.df.apply(calculate_row_entropy, axis=1)
            self.feature_metadata['features']['sensor_entropy'] = 'センサー値のエントロピー'

        return self

    def create_pressure_features(self):
        """圧力関連の特徴量生成"""
        self.logger.info("\n=== 圧力関連特徴量の生成 ===")

        # 圧力比と差分
        if 'A剤流圧_Mpa' in self.df.columns and 'B剤流圧_Mpa' in self.df.columns:
            self.df['pressure_ratio_AB'] = self.df['A剤流圧_Mpa'] / (self.df['B剤流圧_Mpa'] + 1e-10)
            self.df['pressure_diff_AB'] = self.df['A剤流圧_Mpa'] - self.df['B剤流圧_Mpa']
            self.df['pressure_sum_AB'] = self.df['A剤流圧_Mpa'] + self.df['B剤流圧_Mpa']
            self.df['pressure_product_AB'] = self.df['A剤流圧_Mpa'] * self.df['B剤流圧_Mpa']

            # 圧力不均衡度
            self.df['pressure_imbalance'] = abs(self.df['pressure_diff_AB']) / (self.df['pressure_sum_AB'] + 1e-10)

            self.feature_metadata['features']['pressure_ratio_AB'] = 'A剤とB剤の圧力比'
            self.feature_metadata['features']['pressure_diff_AB'] = 'A剤とB剤の圧力差'
            self.feature_metadata['features']['pressure_sum_AB'] = 'A剤とB剤の圧力和'
            self.feature_metadata['features']['pressure_product_AB'] = 'A剤とB剤の圧力積'
            self.feature_metadata['features']['pressure_imbalance'] = '圧力不均衡度'

        # タンク圧力差と平均
        for agent in ['A剤', 'B剤']:
            tank1_col = f'{agent}タンク1圧力_Mpa'
            tank2_col = f'{agent}タンク2圧力_Mpa'
            if tank1_col in self.df.columns and tank2_col in self.df.columns:
                self.df[f'{agent}_tank_pressure_diff'] = abs(self.df[tank1_col] - self.df[tank2_col])
                self.df[f'{agent}_tank_pressure_avg'] = (self.df[tank1_col] + self.df[tank2_col]) / 2
                self.df[f'{agent}_tank_pressure_max'] = self.df[[tank1_col, tank2_col]].max(axis=1)
                self.df[f'{agent}_tank_pressure_min'] = self.df[[tank1_col, tank2_col]].min(axis=1)

                # タンク効率
                self.df[f'{agent}_tank_efficiency'] = (
                    self.df[tank1_col] + self.df[tank1_col]
                ) / (self.df[tank2_col] + self.df[tank2_col] + 1e-10)

                self.feature_metadata['features'][f'{agent}_tank_pressure_diff'] = f'{agent}のタンク間圧力差'
                self.feature_metadata['features'][f'{agent}_tank_pressure_avg'] = f'{agent}のタンク圧力平均'
                self.feature_metadata['features'][f'{agent}_tank_pressure_max'] = f'{agent}のタンク圧力最大'
                self.feature_metadata['features'][f'{agent}_tank_pressure_min'] = f'{agent}のタンク圧力最小'
                self.feature_metadata['features'][f'{agent}_tank_efficiency'] = f'{agent}のタンク効率'

        # 全圧力センサーの統計量
        pressure_cols = [col for col in self.df.columns if 'Mpa' in col and '圧力' in col]
        if pressure_cols:
            self.df['all_pressure_mean'] = self.df[pressure_cols].mean(axis=1)
            self.df['all_pressure_std'] = self.df[pressure_cols].std(axis=1)
            self.df['all_pressure_max'] = self.df[pressure_cols].max(axis=1)
            self.df['all_pressure_min'] = self.df[pressure_cols].min(axis=1)
            self.df['all_pressure_range'] = self.df['all_pressure_max'] - self.df['all_pressure_min']

            self.feature_metadata['features']['all_pressure_mean'] = '全圧力センサーの平均'
            self.feature_metadata['features']['all_pressure_std'] = '全圧力センサーの標準偏差'
            self.feature_metadata['features']['all_pressure_max'] = '全圧力センサーの最大値'
            self.feature_metadata['features']['all_pressure_min'] = '全圧力センサーの最小値'
            self.feature_metadata['features']['all_pressure_range'] = '全圧力センサーのレンジ'

        self.logger.info(f"  生成した圧力特徴量: {len([k for k in self.feature_metadata['features'] if 'pressure' in k.lower()])}個")

        return self

    def create_interaction_features(self):
        """相互作用特徴量の生成"""
        self.logger.info("\n=== 相互作用特徴量の生成 ===")

        # 圧力と配合比の相互作用
        if 'A剤流圧_Mpa' in self.df.columns and 'A剤配合比速度' in self.df.columns:
            self.df['A_pressure_mix_interaction'] = (
                self.df['A剤流圧_Mpa'] * self.df['A剤配合比速度']
            )
            self.feature_metadata['features']['A_pressure_mix_interaction'] = 'A剤圧力×配合比速度'

        if 'B剤流圧_Mpa' in self.df.columns and 'B剤配合比速度' in self.df.columns:
            self.df['B_pressure_mix_interaction'] = (
                self.df['B剤流圧_Mpa'] * self.df['B剤配合比速度']
            )
            self.feature_metadata['features']['B_pressure_mix_interaction'] = 'B剤圧力×配合比速度'

        # 流速とサイクル時間の相互作用
        if '生産総合流速' in self.df.columns and 'total_cycle_time' in self.df.columns:
            self.df['flow_cycle_interaction'] = (
                self.df['生産総合流速'] * self.df['total_cycle_time']
            )
            self.feature_metadata['features']['flow_cycle_interaction'] = '流速×サイクル時間'

        # 多項式特徴量（センサー間の相互作用）
        key_sensors = ['A剤流圧_Mpa', 'B剤流圧_Mpa', '生産総合流速']
        existing_sensors = [col for col in key_sensors if col in self.df.columns]

        if len(existing_sensors) >= 2:
            for i in range(len(existing_sensors)):
                for j in range(i+1, len(existing_sensors)):
                    col1, col2 = existing_sensors[i], existing_sensors[j]
                    feature_name = f'{col1.split("_")[0]}_{col2.split("_")[0]}_product'
                    self.df[feature_name] = self.df[col1] * self.df[col2]
                    self.feature_metadata['features'][feature_name] = f'{col1}×{col2}'

        self.logger.info(f"  生成した相互作用特徴量: {len([k for k in self.feature_metadata['features'] if 'interaction' in k or 'product' in k])}個")

        return self

    def create_threshold_features(self):
        """閾値ベースの異常フラグ生成"""
        self.logger.info("\n=== 閾値ベース異常フラグの生成 ===")

        # 圧力の異常フラグ
        pressure_thresholds = {
            'A剤流圧_Mpa': (0.1, 0.5),  # 最小、最大
            'B剤流圧_Mpa': (0.1, 0.5),
            'A剤タンク1圧力_Mpa': (0.0, 0.2),
            'A剤タンク2圧力_Mpa': (-0.2, 0.2),
            'B剤タンク1圧力_Mpa': (0.0, 0.2),
            'B剤タンク2圧力_Mpa': (-0.2, 0.2)
        }

        for col, (min_val, max_val) in pressure_thresholds.items():
            if col in self.df.columns:
                self.df[f'{col}_low'] = (self.df[col] < min_val).astype(int)
                self.df[f'{col}_high'] = (self.df[col] > max_val).astype(int)

                self.feature_metadata['features'][f'{col}_low'] = f'{col}が下限閾値未満'
                self.feature_metadata['features'][f'{col}_high'] = f'{col}が上限閾値超過'

        # 流速の異常フラグ
        if '生産総合流速' in self.df.columns:
            self.df['flow_rate_zero'] = (self.df['生産総合流速'] == 0).astype(int)
            self.df['flow_rate_low'] = (self.df['生産総合流速'] < 50).astype(int)

            self.feature_metadata['features']['flow_rate_zero'] = '流速ゼロフラグ'
            self.feature_metadata['features']['flow_rate_low'] = '流速低下フラグ'

        # 配合比のバランス異常
        if 'mix_ratio' in self.df.columns:
            self.df['mix_ratio_imbalance'] = abs(self.df['mix_ratio'] - 1.0)
            self.df['mix_ratio_abnormal'] = (
                (self.df['mix_ratio'] < 0.8) | (self.df['mix_ratio'] > 1.2)
            ).astype(int)

            self.feature_metadata['features']['mix_ratio_imbalance'] = '配合比の不均衡度'
            self.feature_metadata['features']['mix_ratio_abnormal'] = '配合比異常フラグ'

        # 閾値ベースの複合異常スコア
        anomaly_flags = []
        if 'A剤流圧_Mpa' in self.df.columns and 'B剤流圧_Mpa' in self.df.columns:
            anomaly_flags.append((self.df['A剤流圧_Mpa'] > 0.4).astype(int) * 2)
            anomaly_flags.append((self.df['B剤流圧_Mpa'] > 0.4).astype(int) * 2)

        if 'mix_ratio' in self.df.columns:
            anomaly_flags.append((abs(self.df['mix_ratio'] - 1.0) > 0.2).astype(int) * 3)

        if 'total_cycle_time' in self.df.columns:
            anomaly_flags.append((self.df['total_cycle_time'] > 100).astype(int) * 1)

        if anomaly_flags:
            self.df['composite_anomaly_score'] = sum(anomaly_flags)
            self.feature_metadata['features']['composite_anomaly_score'] = '複合異常スコア'

        self.logger.info(f"  生成した異常フラグ: {len([k for k in self.feature_metadata['features'] if 'abnormal' in k or 'flag' in k])}個")

        return self

    def create_transform_features(self):
        """変換特徴量の生成"""
        self.logger.info("\n=== 変換特徴量の生成 ===")

        # 対数変換（外れ値の影響を軽減）
        log_candidates = ['パレットR/T_分', '生産総合流速', 'A剤配合比速度', 'B剤配合比速度']
        for col in log_candidates:
            if col in self.df.columns:
                self.df[f'{col}_log'] = np.log1p(abs(self.df[col]))
                self.feature_metadata['features'][f'{col}_log'] = f'{col}の対数変換'

        # 逆数変換（滞留時間などの指標）
        if '生産総合流速' in self.df.columns:
            self.df['flow_rate_inverse'] = 1 / (self.df['生産総合流速'] + 1e-10)
            self.feature_metadata['features']['flow_rate_inverse'] = '流速の逆数（滞留時間指標）'

        return self

    def aggregate_anomaly_scores(self):
        """異常スコアの集約"""
        self.logger.info("\n=== 異常スコアの集約 ===")

        # 異常フラグの合計
        anomaly_cols = [col for col in self.df.columns if any(
            pattern in col for pattern in ['_abnormal', '_high', '_low', '_negative', '_zero', '_flag']
        )]

        if anomaly_cols:
            self.df['total_anomaly_flags'] = self.df[anomaly_cols].sum(axis=1)
            self.df['anomaly_flag_ratio'] = self.df['total_anomaly_flags'] / len(anomaly_cols)

            self.feature_metadata['features']['total_anomaly_flags'] = '異常フラグの合計'
            self.feature_metadata['features']['anomaly_flag_ratio'] = '異常フラグの比率'

        # 圧力関連の異常スコア
        pressure_anomaly_cols = [col for col in anomaly_cols if '圧' in col or 'Mpa' in col]
        if pressure_anomaly_cols:
            self.df['pressure_anomaly_score'] = self.df[pressure_anomaly_cols].sum(axis=1)
            self.feature_metadata['features']['pressure_anomaly_score'] = '圧力異常スコア'

        # 時間関連の異常スコア
        time_anomaly_cols = [col for col in anomaly_cols if 'duration' in col or 'time' in col]
        if time_anomaly_cols:
            self.df['time_anomaly_score'] = self.df[time_anomaly_cols].sum(axis=1)
            self.feature_metadata['features']['time_anomaly_score'] = '時間異常スコア'

        self.logger.info(f"  集約した異常スコア: {len([k for k in self.feature_metadata['features'] if 'anomaly' in k and 'score' in k])}個")

        return self

    def handle_missing_values(self):
        """欠損値の処理"""
        self.logger.info("\n=== 欠損値処理 ===")

        # デバッグ: datetime成分カラムの確認
        datetime_component_cols = [col for col in self.df.columns
                                  if any(suffix in col for suffix in ['_hour', '_dayofweek', '_day', '_month'])
                                  and not col in config.DATETIME_COLUMNS]
        self.logger.info(f"  欠損値処理前の日時成分カラム数: {len(datetime_component_cols)}個")

        # 数値カラムの欠損値を0で補完
        numeric_cols = self.df.select_dtypes(include=['float64', 'int64', 'Int64']).columns
        for col in numeric_cols:
            if self.df[col].isna().sum() > 0:
                self.df[col] = self.df[col].fillna(0)

        # カテゴリカル変数の欠損値を'Unknown'で補完
        object_cols = self.df.select_dtypes(include=['object']).columns
        for col in object_cols:
            if self.df[col].isna().sum() > 0:
                self.df[col] = self.df[col].fillna('Unknown')

        return self

    def scale_features(self):
        """特徴量のスケーリング"""
        self.logger.info("\n=== 特徴量のスケーリング ===")

        # スケーリング対象のカラムを選定
        exclude_patterns = ['_datetime', '_encoded', '_frequency', '_flag', '_abnormal', '_score']
        datetime_original = config.DATETIME_COLUMNS

        numeric_cols = self.df.select_dtypes(include=['float64', 'int64', 'Int64']).columns
        scale_cols = []

        # デバッグ用: datetime関連のカラムを追跡
        datetime_component_cols = []

        # デバッグ: 現在のカラムを確認
        all_datetime_cols = [col for col in self.df.columns
                           if any(suffix in col for suffix in ['_hour', '_dayofweek', '_day', '_month'])
                           and not col in config.DATETIME_COLUMNS]
        self.logger.info(f"  スケーリング前の全日時成分カラム数: {len(all_datetime_cols)}個")

        # デバッグ: 日時カラムがnumeric_colsに含まれるか確認
        datetime_in_numeric = [col for col in all_datetime_cols if col in numeric_cols]
        self.logger.info(f"  数値型として認識された日時成分カラム: {len(datetime_in_numeric)}個")

        for col in numeric_cols:
            # 除外パターンに該当しない、かつ元の日時カラムでない場合
            if not any(pattern in col for pattern in exclude_patterns) and col not in datetime_original:
                # バイナリフラグ（0/1のみ）は除外、ただし単一値のカラムは除外しない
                # (単一値でもモデルの一貫性のためにスケーリング列を作成する)
                unique_vals = self.df[col].unique()
                is_binary = (self.df[col].nunique() == 2) and (set(unique_vals) <= {0, 1})

                if not is_binary:
                    scale_cols.append(col)
                    # デバッグ: datetime成分カラムを記録
                    if any(suffix in col for suffix in ['_hour', '_dayofweek', '_day', '_month']):
                        datetime_component_cols.append(col)

        # デバッグログ
        self.logger.info(f"  スケーリング対象の日時成分カラム: {len(datetime_component_cols)}個")

        # ロバストスケーリング
        for col in scale_cols:
            Q1 = self.df[col].quantile(0.25)
            Q3 = self.df[col].quantile(0.75)
            IQR = Q3 - Q1

            if IQR > 0:
                self.df[f'{col}_scaled'] = (self.df[col] - Q1) / IQR
            else:
                # IQRが0の場合は、値を0にスケーリング
                # (モデルの一貫性のために列は必ず作成する)
                self.df[f'{col}_scaled'] = 0.0

            self.feature_metadata['features'][f'{col}_scaled'] = f'{col}のロバストスケール値'

        self.logger.info(f"  スケーリングした特徴量: {len(scale_cols)}個")

        return self

    def save_features(self):
        """特徴量の保存"""
        self.logger.info("\n=== 特徴量の保存 ===")

        # 入力ファイル名から動的に出力ファイル名を生成
        input_filename = self.data_path.name
        output_filename = config.get_phase3_output_filename(input_filename, 'features')
        metadata_filename = config.get_phase3_output_filename(input_filename, 'metadata')

        # 出力パス
        output_dir = self.data_path.parent
        output_path = output_dir / output_filename
        metadata_path = output_dir / metadata_filename

        # CSVの保存
        self.df.to_csv(output_path, index=False, encoding='utf-8-sig')
        self.logger.info(f"メインファイル: {output_path}")
        self.logger.info(f"  最終的なレコード数: {len(self.df):,}")
        self.logger.info(f"  最終的なカラム数: {len(self.df.columns)}")

        # メタデータの保存
        self.feature_metadata['engineered_features'] = [
            col for col in self.df.columns
            if col not in self.feature_metadata['original_columns']
        ]

        with open(metadata_path, 'w', encoding='utf-8') as f:
            json.dump(self.feature_metadata, f, ensure_ascii=False, indent=2)
        self.logger.info(f"メタデータファイル: {metadata_path}")

        return self

    def filter_features_for_top25(self):
        """
        TOP25モードの場合、TOP25特徴量のみを残す

        処理の流れ:
        1. TOP25に含まれる特徴量のみを保持
        2. 元の列やその他の生成された特徴量はすべて削除

        注意: この処理は scale_features() の後に実行されることを前提としています。
              _scaled特徴量は既に生成済みで、元の特徴量は不要になっています。
        """
        if self.feature_mode != 'top25':
            return self

        self.logger.info("\n=== TOP25特徴量フィルタリング ===")

        # フィルタリング前のカラム数
        before_count = len(self.df.columns)

        # 保持するカラムのセット（TOP25のみ）
        keep_columns = set()

        # TOP25特徴量を追加
        for feature in config.TOP_25_IMPORTANT_FEATURES:
            if feature in self.df.columns:
                keep_columns.add(feature)
            else:
                self.logger.warning(f"  警告: TOP25特徴量が見つかりません: {feature}")

        # Deployment scoring needs these identifiers even when they are not model inputs.
        for column in config.PHASE3_PASSTHROUGH_COLUMNS:
            if column in self.df.columns:
                keep_columns.add(column)

        # 不要なカラムを削除
        cols_to_drop = [col for col in self.df.columns if col not in keep_columns]

        if cols_to_drop:
            self.df.drop(columns=cols_to_drop, inplace=True)
            self.logger.info(f"  削除した特徴量: {len(cols_to_drop)}個")
            self.logger.info(f"  {before_count}列 → {len(self.df.columns)}列")
            self.logger.info(f"  保持したTOP25特徴量: {len(keep_columns)}個")

            # メタデータから削除した特徴量を除外
            for col in cols_to_drop:
                if col in self.feature_metadata['features']:
                    del self.feature_metadata['features'][col]
        else:
            self.logger.info("  削除する特徴量はありません")

        return self

    def run(self):
        """特徴量エンジニアリングの実行"""
        self.logger.info("\n" + "=" * 60)
        self.logger.info("モールド装置データの特徴量エンジニアリング開始")
        self.logger.info(f"モード: {self.feature_mode.upper()}")
        self.logger.info("=" * 60)

        self.load_data()
        self.standardize_datetime_columns()  # 日時形式の統一
        self.create_time_features()  # 時間成分の抽出
        self.create_process_time_features()  # プロセス時間

        # fullモードの場合のみ、追加の特徴量を生成
        if self.feature_mode == 'full':
            self.create_physical_features()  # 物理法則ベース
            self.create_quality_features()  # 品質スコア
            self.create_entropy_features()  # エントロピー
            self.create_pressure_features()  # 圧力関連
            self.create_interaction_features()  # 相互作用

        self.create_threshold_features()  # 閾値ベース異常
        self.create_transform_features()  # 変換特徴量
        self.aggregate_anomaly_scores()  # 異常スコア集約
        self.handle_missing_values()  # 欠損値処理
        self.scale_features()  # スケーリング

        # TOP25モードの場合、必要な特徴量のみをフィルタリング
        if self.feature_mode == 'top25':
            self.filter_features_for_top25()

        self.save_features()  # 保存

        self.logger.info("\n" + "=" * 60)
        self.logger.info("特徴量エンジニアリング完了")
        self.logger.info(f"モード: {self.feature_mode.upper()}")
        self.logger.info(f"生成された特徴量数: {len(self.feature_metadata.get('engineered_features', []))}")
        self.logger.info(f"最終カラム数: {len(self.df.columns)}")
        self.logger.info("=" * 60)

        return self


def analyze_daily_data_count(data_path, output_dir=None):
    """
    異常検知対象データの日別データ件数を集計

    Parameters:
    -----------
    data_path : str or Path
        入力CSVファイルのパス
    output_dir : str or Path
        出力ディレクトリ（デフォルト: ../output/reports）

    Returns:
    --------
    dict : 集計結果の辞書
    """
    print("\n=== 日別データ件数集計 ===")

    # 出力ディレクトリの設定（Noneの場合はプロジェクトルートからの絶対パスを使用）
    if output_dir is None:
        # このファイルの場所からプロジェクトルートを特定
        current_file = Path(__file__).resolve()
        project_root = current_file.parent.parent  # src/phase3.py -> alert-logic/
        output_dir = project_root / 'output' / 'reports'

    # データ読み込み
    data_path = Path(data_path)
    print(f"データ読み込み中: {data_path.name}")

    try:
        # エンコーディングを試行
        for encoding in ['shift-jis', 'cp932', 'utf-8-sig', 'utf-8']:
            try:
                df = pd.read_csv(data_path, encoding=encoding)
                print(f"  エンコーディング: {encoding}")
                break
            except UnicodeDecodeError:
                continue
    except Exception as e:
        print(f"エラー: データ読み込みに失敗しました: {e}")
        return None

    # 生産日列の確認
    date_column = None
    for col in ['生産日', '注入開始日時', '日付', 'date']:
        if col in df.columns:
            date_column = col
            break

    if date_column is None:
        print("警告: 日付列が見つかりません")
        return None

    print(f"  日付列: {date_column}")

    # 日付形式の変換（Excel形式の場合の処理を含む）
    def convert_to_date(value):
        """様々な形式の日付を標準形式に変換"""
        if pd.isna(value):
            return None

        # 数値の場合（Excel形式）
        if isinstance(value, (int, float)):
            try:
                # Excel形式の日付を変換
                return pd.to_datetime('1899-12-30') + pd.Timedelta(days=int(value))
            except:
                return None

        # 文字列の場合
        if isinstance(value, str):
            try:
                # 複数の日付形式を試行
                for fmt in ['%Y/%m/%d', '%Y-%m-%d', '%Y年%m月%d日', '%Y%m%d']:
                    try:
                        return pd.to_datetime(value, format=fmt)
                    except:
                        continue
                # フォーマット指定なしで試行
                return pd.to_datetime(value)
            except:
                return None

        return None

    # 日付列を変換
    df['converted_date'] = df[date_column].apply(convert_to_date)

    # 変換成功率を確認
    valid_dates = df['converted_date'].notna().sum()
    print(f"  変換成功: {valid_dates}/{len(df)} ({valid_dates/len(df)*100:.1f}%)")

    # 日付でグループ化して件数を集計
    df['date_only'] = pd.to_datetime(df['converted_date']).dt.date
    daily_counts = df.groupby('date_only').size()

    # 結果をJSON形式で準備
    result = {
        'file': data_path.name,
        'total_records': len(df),
        'valid_dates': int(valid_dates),
        'date_range': {
            'start': str(daily_counts.index.min()) if len(daily_counts) > 0 else None,
            'end': str(daily_counts.index.max()) if len(daily_counts) > 0 else None
        },
        'daily_counts': {str(date): int(count) for date, count in daily_counts.items()}
    }

    # 統計情報を追加
    if len(daily_counts) > 0:
        result['statistics'] = {
            'mean': float(daily_counts.mean()),
            'median': float(daily_counts.median()),
            'std': float(daily_counts.std()),
            'min': int(daily_counts.min()),
            'max': int(daily_counts.max())
        }

    # JSONファイルとして保存
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    output_file = output_dir / config.PHASE3_DAILY_DATA_COUNTS_FILE
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\n集計結果を保存しました: {output_file}")
    print(f"  期間: {result['date_range']['start']} ~ {result['date_range']['end']}")
    print(f"  総データ件数: {result['total_records']:,}")

    if 'statistics' in result:
        print(f"  日次データ件数:")
        print(f"    平均: {result['statistics']['mean']:.1f}")
        print(f"    中央値: {result['statistics']['median']:.1f}")
        print(f"    最小: {result['statistics']['min']}")
        print(f"    最大: {result['statistics']['max']}")

    return result


def main():
    """メイン処理

    コマンドライン引数:
        --mode train : モデル構築モード（学習・テスト両データを処理）
        --mode predict : 予測モード（予測データのみを処理）
        --feature-mode full : 全特徴量を生成
        --feature-mode top25 : TOP25特徴量のみ生成（デフォルト）
        ファイルパス : 処理対象ファイルを直接指定（省略時はconfig設定を使用）
    """
    import argparse

    # コマンドライン引数の解析
    parser = argparse.ArgumentParser(
        description='Phase 3: AI異常検知のための特徴量エンジニアリング'
    )
    parser.add_argument(
        '--mode',
        choices=['train', 'predict'],
        default=config.PHASE3_DEFAULT_MODE,
        help='実行モード: train（モデル構築）またはpredict（予測）'
    )
    parser.add_argument(
        '--feature-mode',
        choices=['full', 'top25'],
        default=config.PHASE3_FEATURE_MODE,
        help='特徴量生成モード: full（全特徴量）またはtop25（重要特徴量のみ）'
    )
    parser.add_argument(
        'files',
        nargs='*',
        help='処理対象ファイル（省略時はconfig設定を使用）'
    )

    args = parser.parse_args()

    # モードに応じた対象ファイルの決定
    if args.files:
        # ファイルが指定されている場合はそれを使用
        target_files = args.files
    else:
        # モードに応じたデフォルトファイルを選択
        if args.mode == 'train':
            # モデル構築モード：両方のファイルを処理
            target_files = [
                f'data/{config.CONTROL_LIMIT_CALCULATION_FILE}',  # 学習用
                f'data/{config.ANOMALY_DETECTION_FILE}'  # テスト用
            ]
        else:  # predict
            # 予測モード：予測データのみを処理
            target_files = [
                f'data/{config.ANOMALY_DETECTION_FILE}'  # 予測用
            ]

    # ヘッダー表示
    print("\n" + "=" * 70)
    print("Phase 3: AI異常検知のための特徴量エンジニアリング")
    print("=" * 70)
    print(f"実行モード: {args.mode.upper()}")
    print(f"特徴量モード: {args.feature_mode.upper()}")

    if args.mode == 'train':
        print("  説明: モデル構築用に学習データとテストデータを処理します")
    else:
        print("  説明: 運用時の予測用にデータを処理します")

    if args.feature_mode == 'full':
        print("  特徴量: 全特徴量を生成します")
    else:
        print(f"  特徴量: DataRobot重要度TOP25の特徴量のみを生成します")

    print(f"処理対象ファイル数: {len(target_files)}")
    for f in target_files:
        print(f"  - {Path(f).name}")

    # 異常検知対象ファイルの日別集計（どちらのモードでも実行）
    anomaly_file = f'data/{config.ANOMALY_DETECTION_FILE}'
    if anomaly_file in target_files:
        print(f"\n=== 日別データ件数集計 ===")
        print(f"対象データ: {config.ANOMALY_DETECTION_FILE}")
        analyze_daily_data_count(anomaly_file)

    # 各ファイルに対して特徴量エンジニアリングを実行
    print("\n=== 特徴量エンジニアリング ===")
    for file_path in target_files:
        file_path = Path(file_path)

        if not file_path.exists():
            print(f"\n警告: ファイルが存在しません: {file_path}")
            continue

        print(f"\n処理対象ファイル: {file_path.name}")
        print("-" * 60)

        # 特徴量エンジニアリング実行（feature_modeを渡す）
        feature_eng = MoldFeatureEngineering(file_path, feature_mode=args.feature_mode)
        feature_eng.run()

    print("\n" + "=" * 70)
    print(f"Phase 3 処理完了")
    print(f"  実行モード: {args.mode.upper()}")
    print(f"  特徴量モード: {args.feature_mode.upper()}")
    print("=" * 70)

    # モードに応じた次のステップのガイダンス
    if args.mode == 'train':
        print("\n次のステップ:")
        print("  1. 生成された特徴量ファイルを使用してAIモデルを学習")
        print(f"     - 学習データ: {config.CONTROL_LIMIT_CALCULATION_FILE.replace('.csv', '_features.csv')}")
        print(f"     - テストデータ: {config.ANOMALY_DETECTION_FILE.replace('.csv', '_features.csv')}")
        print("  2. モデルの性能評価と調整")
    else:
        print("\n次のステップ:")
        print("  1. 生成された特徴量ファイルを学習済みモデルに入力")
        print(f"     - 予測データ: {config.ANOMALY_DETECTION_FILE.replace('.csv', '_features.csv')}")
        print("  2. 異常スコアの算出と閾値判定")
        print("  3. 異常検知結果のレポート生成")


if __name__ == "__main__":
    main()