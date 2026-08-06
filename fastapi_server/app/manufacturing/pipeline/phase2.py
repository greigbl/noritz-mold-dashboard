"""
Phase 2: 新JIS X-R管理図による異常検知

新JIS規格の8つの異常判定ルールに基づき、管理図による異常検知を実行します。
複数の特性値（ターゲットカラム）に対して、全吐出パターン番号との組み合わせで異常判定を行います。
"""

import json
import pandas as pd
import numpy as np
import matplotlib
import matplotlib.pyplot as plt
import seaborn as sns
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple
import logging
import warnings
from matplotlib import font_manager, ft2font

from app.manufacturing.pipeline.phase1 import load_data
from app.manufacturing.pipeline.config import (
    TARGET_COLUMNS,
    D2_TABLE,
    SAVE_FIGURES,
    ANOMALY_DETECTION_FILE,
    DETECTION_DAYS,
    PLOT_DAYS,
    PHASE1_MISSING_IDS_JSON,
)
from app.manufacturing.pipeline.utils import aggregate_daily


class XRControlChart:
    """新JIS X-R管理図による異常検知クラス"""

    def __init__(
        self,
        log_dir: str = "../logs",
        output_dir: str = "../output",
        target_columns: List[str] = None,
    ):
        """
        初期化

        Args:
            log_dir: ログディレクトリ
            output_dir: 出力ディレクトリ
            target_columns: 管理対象の特性値列名リスト（Noneの場合はTARGET_COLUMNS全て）
        """
        self.log_dir = Path(log_dir)
        self.output_dir = Path(output_dir)
        self.target_columns = (
            target_columns if target_columns is not None else TARGET_COLUMNS
        )
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # ディレクトリ作成
        self.log_dir.mkdir(parents=True, exist_ok=True)
        (self.output_dir / "figures").mkdir(parents=True, exist_ok=True)
        (self.output_dir / "reports").mkdir(parents=True, exist_ok=True)

        # ロガー設定
        self._setup_logger()

        # d2係数テーブル（configから読み込み）
        self.d2_table = D2_TABLE

        # 日本語フォント設定
        self._setup_japanese_font()

    def _setup_logger(self):
        """ロガー設定"""
        self.log_file = self.log_dir / f"phase2_xr_control_chart_{self.timestamp}.log"

        # ロガー作成
        self.logger = logging.getLogger("Phase2")
        self.logger.setLevel(logging.INFO)
        self.logger.handlers.clear()

        # ファイルハンドラ
        file_handler = logging.FileHandler(self.log_file, encoding="utf-8")
        file_handler.setLevel(logging.INFO)

        # コンソールハンドラ
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)

        # フォーマッタ
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)

        self.logger.addHandler(file_handler)
        self.logger.addHandler(console_handler)

        self.logger.info("Phase 2 X-R管理図異常検知 開始")
        self.logger.info(f"ログファイル: {self.log_file}")

    def _setup_japanese_font(self):
        """日本語フォント設定"""
        warnings.filterwarnings("ignore")

        jp_test_text = "日本語吐出パターン管理図"
        preferred_fonts = [
            "Hiragino Sans",
            "Hiragino Kaku Gothic ProN",
            "Yu Gothic",
            "Meiryo",
            "Arial Unicode MS",
        ]

        def supports_japanese(font_path: str, text: str) -> bool:
            try:
                cmap = ft2font.FT2Font(font_path).get_charmap()
                return all((ord(ch) in cmap) for ch in text if ch.strip())
            except Exception:
                return False

        self.font_name = None
        for preferred in preferred_fonts:
            for font in font_manager.fontManager.ttflist:
                if font.name == preferred and supports_japanese(
                    font.fname, jp_test_text
                ):
                    self.font_name = font.name
                    break
            if self.font_name:
                break

        if self.font_name:
            matplotlib.rcParams["font.family"] = self.font_name
            matplotlib.rcParams["font.sans-serif"] = [self.font_name]
            self.logger.info(f"使用フォント: {self.font_name}")
        else:
            self.logger.warning("日本語表示可能なフォントが見つかりません")
            self.font_name = "sans-serif"  # フォールバック

        matplotlib.rcParams["axes.unicode_minus"] = False
        sns.set_style("whitegrid")
        plt.rcParams["figure.figsize"] = (16, 8)
        plt.rcParams["font.size"] = 10

    @staticmethod
    def excel_serial_to_datetime(serial):
        """Excelシリアル値をdatetimeに変換"""
        if pd.isna(serial):
            return pd.NaT
        try:
            base_date = datetime(1899, 12, 30)
            return base_date + pd.Timedelta(days=float(serial))
        except (ValueError, TypeError, OverflowError):
            return pd.NaT

    def load_clean_data(
        self, data_path: str, missing_ids_path: str = None
    ) -> pd.DataFrame:
        """
        正常データを読み込み

        Args:
            data_path: オリジナルデータのパス
            missing_ids_path: missing_idsファイルのパス（Noneの場合は最新を自動検出）

        Returns:
            正常データのDataFrame
        """
        # オリジナルデータ読み込み
        self.logger.info(f"データ読み込み: {data_path}")
        df_original = load_data(data_path)
        self.logger.info(f"オリジナルデータ: {len(df_original):,}行")

        # missing_idsを読み込み
        if missing_ids_path is None:
            reports_dir = self.output_dir / "reports"
            missing_ids_path = reports_dir / PHASE1_MISSING_IDS_JSON

            if not missing_ids_path.exists():
                raise FileNotFoundError(
                    f"{PHASE1_MISSING_IDS_JSON}ファイルが見つかりません。Phase 1を先に実行してください。"
                )

            self.logger.info(f"使用するmissing_ids: {missing_ids_path.name}")

        with open(missing_ids_path, "r", encoding="utf-8") as f:
            missing_data = json.load(f)

        self.logger.info(
            f"欠損行情報: タイムスタンプ={missing_data['timestamp']}, 欠損行数={missing_data['missing_rows_count']:,}"
        )

        # 欠損行を除外
        missing_indices = missing_data["missing_indices"]
        df_clean = df_original.drop(index=missing_indices)

        self.logger.info(
            f"正常データ: {len(df_clean):,}行（欠損除外: {len(missing_indices):,}行）"
        )

        return df_clean

    def load_control_limits(
        self, control_limits_path: str = None
    ) -> Dict[str, Dict[int, Dict[str, float]]]:
        """
        Phase 0で保存した管理限界パラメータを読み込み

        Args:
            control_limits_path: 管理限界JSONファイルのパス（Noneの場合は最新を自動検出）

        Returns:
            管理限界の辞書 {ターゲットカラム: {吐出パターン番号: {CL, UCL, LCL, ...}}}
        """
        if control_limits_path is None:
            control_limits_file = (
                self.output_dir / "reports" / "phase0_control_limits.json"
            )

            if not control_limits_file.exists():
                raise FileNotFoundError(
                    f"管理限界ファイルが見つかりません: {control_limits_file}\n"
                    "Phase 0を先に実行してください。"
                )

            control_limits_path = control_limits_file
            self.logger.info(f"使用する管理限界: {control_limits_path.name}")
        else:
            control_limits_path = Path(control_limits_path)

        with open(control_limits_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        self.logger.info(
            f"管理限界読み込み: タイムスタンプ={data['timestamp']}, パターン数={data['pattern_count']}, ターゲットカラム数={len(data['target_columns'])}"
        )

        # Support both JSON layouts:
        # - legacy: {ターゲットカラム: {吐出パターン番号: 管理限界}}
        # - current: {吐出パターン番号: {ターゲットカラム: 管理限界}}
        control_limits: dict[str, dict[int, dict]] = {}
        payload = data["control_limits"]
        sample_key = next(iter(payload))

        if str(sample_key).isdigit():
            for pattern_str, targets in payload.items():
                pattern_num = int(pattern_str)
                for target_col, limits in targets.items():
                    control_limits.setdefault(target_col, {})[pattern_num] = limits
        else:
            for target_col, patterns in payload.items():
                control_limits[target_col] = {}
                for pattern_str, limits in patterns.items():
                    control_limits[target_col][int(pattern_str)] = limits

        return control_limits

    def calculate_control_limits(self, pattern_data: pd.DataFrame) -> Dict[str, float]:
        """
        管理限界を計算

        Args:
            pattern_data: 特定の吐出パターンのデータ

        Returns:
            管理限界の辞書
        """
        # X̄（全体平均）
        x_double_bar = pattern_data["平均"].mean()

        # R̄（範囲の平均）
        r_bar = pattern_data["範囲_R"].mean()

        # σの推定値（R̄/d2を使用）
        n = int(pattern_data["サンプル数"].median())
        d2 = self.d2_table.get(min(n, 10), 2.059)
        sigma = r_bar / d2

        # 管理限界
        ucl = x_double_bar + 3 * sigma
        lcl = x_double_bar - 3 * sigma

        # 領域境界
        upper_2sigma = x_double_bar + 2 * sigma
        upper_1sigma = x_double_bar + 1 * sigma
        lower_1sigma = x_double_bar - 1 * sigma
        lower_2sigma = x_double_bar - 2 * sigma

        return {
            "CL": x_double_bar,
            "UCL": ucl,
            "LCL": lcl,
            "sigma": sigma,
            "upper_2sigma": upper_2sigma,
            "upper_1sigma": upper_1sigma,
            "lower_1sigma": lower_1sigma,
            "lower_2sigma": lower_2sigma,
            "n": n,
            "d2": d2,
        }

    def check_new_jis_rules(
        self, values: np.ndarray, limits: Dict[str, float]
    ) -> List[List[int]]:
        """
        新JIS 8つのルールで異常を判定

        Args:
            values: 時系列データ（平均値のリスト）
            limits: 管理限界の辞書

        Returns:
            異常検出結果のリスト（各点に対してどのルールに違反したか）
        """
        n = len(values)
        anomalies = [[] for _ in range(n)]

        CL = limits["CL"]
        UCL = limits["UCL"]
        LCL = limits["LCL"]
        upper_2sigma = limits["upper_2sigma"]
        upper_1sigma = limits["upper_1sigma"]
        lower_1sigma = limits["lower_1sigma"]
        lower_2sigma = limits["lower_2sigma"]

        for i in range(n):
            # ルール1: 領域Aを超えている点が1つ
            if values[i] > UCL or values[i] < LCL:
                anomalies[i].append(1)

            # ルール2: 連続する9点が中心線に対して同じ側にある
            if i >= 8:
                window = values[i - 8 : i + 1]
                if all(v > CL for v in window) or all(v < CL for v in window):
                    for j in range(i - 8, i + 1):
                        if 2 not in anomalies[j]:
                            anomalies[j].append(2)

            # ルール3: 連続する6点が増加、又は減少している
            if i >= 5:
                window = values[i - 5 : i + 1]
                increasing = all(window[j] < window[j + 1] for j in range(5))
                decreasing = all(window[j] > window[j + 1] for j in range(5))
                if increasing or decreasing:
                    for j in range(i - 5, i + 1):
                        if 3 not in anomalies[j]:
                            anomalies[j].append(3)

            # ルール4: 14点が交互に増減している
            if i >= 13:
                window = values[i - 13 : i + 1]
                alternating = all(
                    (window[j] < window[j + 1] and window[j + 1] > window[j + 2])
                    or (window[j] > window[j + 1] and window[j + 1] < window[j + 2])
                    for j in range(12)
                )
                if alternating:
                    for j in range(i - 13, i + 1):
                        if 4 not in anomalies[j]:
                            anomalies[j].append(4)

            # ルール5: 連続する3点中、2点が領域A又はそれを超えた領域にある（>2σ）
            if i >= 2:
                window = values[i - 2 : i + 1]
                count_in_zone_a = sum(
                    1 for v in window if v > upper_2sigma or v < lower_2sigma
                )
                if count_in_zone_a >= 2:
                    for j in range(i - 2, i + 1):
                        if 5 not in anomalies[j]:
                            anomalies[j].append(5)

            # ルール6: 連続する5点中、4点が領域B又はそれを超えた領域にある（>1σ）
            if i >= 4:
                window = values[i - 4 : i + 1]
                count_beyond_1sigma = sum(
                    1 for v in window if v > upper_1sigma or v < lower_1sigma
                )
                if count_beyond_1sigma >= 4:
                    for j in range(i - 4, i + 1):
                        if 6 not in anomalies[j]:
                            anomalies[j].append(6)

            # ルール7: 連続する15点が領域Cに存在する（≤1σ）
            if i >= 14:
                window = values[i - 14 : i + 1]
                if all(lower_1sigma <= v <= upper_1sigma for v in window):
                    for j in range(i - 14, i + 1):
                        if 7 not in anomalies[j]:
                            anomalies[j].append(7)

            # ルール8: 連続する8点が領域Cを超えた領域にある（>1σ）
            if i >= 7:
                window = values[i - 7 : i + 1]
                if all(v > upper_1sigma or v < lower_1sigma for v in window):
                    for j in range(i - 7, i + 1):
                        if 8 not in anomalies[j]:
                            anomalies[j].append(8)

        return anomalies

    def detect_anomalies(
        self,
        daily_stats: pd.DataFrame,
        target_column: str,
        phase0_control_limits: Dict[str, Dict[int, Dict[str, float]]],
        detection_days: int = DETECTION_DAYS,
    ) -> Tuple[pd.DataFrame, Dict[Tuple[int, str], Dict[str, float]]]:
        """
        全吐出パターンに対して異常検知（Phase 0の管理限界を使用、直近N日間のみ判定）

        Args:
            daily_stats: 日次集計データ
            target_column: 対象の特性値列名
            phase0_control_limits: Phase 0で計算した管理限界の辞書
            detection_days: 異常判定対象期間（直近N日間）

        Returns:
            (異常データのDataFrame, 管理限界の辞書)
        """
        all_anomalies = []
        control_limits = {}

        # 直近N日間の日付範囲を計算
        max_date = daily_stats["注入開始日"].max()
        cutoff_date = max_date - pd.Timedelta(days=detection_days - 1)

        for pattern_num in sorted(daily_stats["吐出パターン番号"].unique()):
            pattern_data = daily_stats[
                daily_stats["吐出パターン番号"] == pattern_num
            ].sort_values("注入開始日")

            # Phase 0の管理限界を使用
            if (
                target_column in phase0_control_limits
                and pattern_num in phase0_control_limits[target_column]
            ):
                limits = phase0_control_limits[target_column][pattern_num]
                self.logger.debug(
                    f"  パターン{pattern_num}: Phase 0の管理限界を使用 (CL={limits['CL']:.4f})"
                )
            else:
                # Phase 0に該当データがない場合は警告を出してスキップ
                self.logger.warning(
                    f"  パターン{pattern_num}: Phase 0に管理限界が存在しません。スキップします。"
                )
                continue

            control_limits[(pattern_num, target_column)] = limits

            # 全期間のデータで異常判定（連続性の検出のため）
            values = pattern_data["平均"].values
            anomalies = self.check_new_jis_rules(values, limits)

            # 異常データを記録（直近N日間のみ）
            for idx, (_, row) in enumerate(pattern_data.iterrows()):
                # 直近N日間の範囲内かチェック
                if row["注入開始日"] >= cutoff_date:
                    if anomalies[idx]:
                        all_anomalies.append(
                            {
                                "吐出パターン番号": pattern_num,
                                "ターゲットカラム": target_column,
                                "注入開始日": row["注入開始日"],
                                "平均値": row["平均"],
                                "違反ルール": anomalies[idx],
                                "CL": limits["CL"],
                                "UCL_3sigma": limits["UCL"],
                                "LCL_3sigma": limits["LCL"],
                                "上側2sigma": limits["upper_2sigma"],
                                "下側2sigma": limits["lower_2sigma"],
                                "上側1sigma": limits["upper_1sigma"],
                                "下側1sigma": limits["lower_1sigma"],
                            }
                        )

        anomalies_df = pd.DataFrame(all_anomalies)

        return anomalies_df, control_limits

    def save_results(
        self,
        anomalies_df: pd.DataFrame,
        all_daily_stats: pd.DataFrame,
        total_original: int,
        total_clean: int,
    ) -> Path:
        """
        結果を保存

        Args:
            anomalies_df: 異常データのDataFrame
            all_daily_stats: 全ターゲットカラムの日次集計データ
            total_original: オリジナルデータの行数
            total_clean: 正常データの行数

        Returns:
            保存したCSVファイルのパス
        """
        self.logger.info("結果保存開始")

        # 日次集計データを上書き保存（タイムスタンプなし、固定ファイル名）
        daily_stats_path = self.output_dir / "reports" / "phase2_daily_stats.csv"
        all_daily_stats.to_csv(daily_stats_path, index=False, encoding="utf-8-sig")
        self.logger.info(
            f"日次集計データ保存（上書き）: {daily_stats_path} ({len(all_daily_stats)}件)"
        )

        # 異常データをCSV保存
        output_path = None
        if len(anomalies_df) > 0:
            # CSV保存用のコピーを作成（元データは保持）
            anomalies_df_save = anomalies_df.copy()

            # 違反ルールを文字列に変換（リスト形式を保持）
            anomalies_df_save["違反ルール"] = anomalies_df_save["違反ルール"].apply(
                lambda x: str(x)  # Pythonのリスト表現をそのまま文字列化 "[2, 3]"
            )
            anomalies_df_save["違反ルール_str"] = anomalies_df_save["違反ルール"].apply(
                lambda x: x.strip("[]").replace(" ", "")  # カンマ区切り用 "2,3"
            )

            # 上書き保存
            output_path = self.output_dir / "reports" / "phase2_anomalies.csv"
            # quoting=1でダブルクォートを強制（QUOTE_MINIMAL）
            anomalies_df_save.to_csv(
                output_path,
                index=False,
                encoding="utf-8-sig",
                quoting=1  # csv.QUOTE_MINIMAL - 必要に応じてクォート
            )

            self.logger.info(f"異常データ保存: {output_path} ({len(anomalies_df)}件)")
        else:
            self.logger.info("異常が検出されなかったため、CSVは保存されません")

        # サマリーレポート保存（上書き保存）
        summary_path = self.output_dir / "reports" / "phase2_summary.txt"
        with open(summary_path, "w", encoding="utf-8") as f:
            f.write("=" * 80 + "\n")
            f.write("Phase 2: 新JIS X-R管理図による異常検知 サマリーレポート\n")
            f.write("=" * 80 + "\n\n")
            f.write(f"実行日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"管理対象特性値: {len(self.target_columns)}種類\n")
            f.write(f"  {', '.join(self.target_columns)}\n\n")
            f.write("入力データ:\n")
            f.write(f"  オリジナルデータ: {total_original:,}行\n")
            f.write(f"  正常データ（Phase 1後）: {total_clean:,}行\n\n")
            f.write("集計データ:\n")
            f.write(
                f"  吐出パターン数: {all_daily_stats['吐出パターン番号'].nunique()}\n"
            )
            f.write(
                f"  ターゲットカラム数: {all_daily_stats['ターゲットカラム'].nunique()}\n"
            )
            f.write(f"  総データ点数: {len(all_daily_stats)}\n\n")
            f.write("異常検出結果:\n")
            f.write(f"  異常検出数: {len(anomalies_df)}件\n")

            if len(anomalies_df) > 0:
                f.write(
                    f"  異常検出率: {len(anomalies_df) / len(all_daily_stats) * 100:.2f}%\n\n"
                )

                # ターゲットカラム別の異常数
                f.write("ターゲットカラム別異常検出数:\n")
                target_counts = anomalies_df["ターゲットカラム"].value_counts()
                for target, count in target_counts.items():
                    f.write(f"  {target}: {count}件\n")
                f.write("\n")

                # ルール別の異常数を集計
                rule_counts = {}
                for rules in anomalies_df["違反ルール"]:
                    for rule in rules:
                        rule_counts[rule] = rule_counts.get(rule, 0) + 1

                f.write("ルール別異常検出数:\n")
                for rule_num in sorted(rule_counts.keys()):
                    f.write(f"  ルール{rule_num}: {rule_counts[rule_num]}件\n")

            f.write("\n" + "=" * 80 + "\n")

        self.logger.info(f"サマリーレポート保存: {summary_path}")

        return output_path

    def plot_control_chart(
        self,
        pattern_num: int,
        target_column: str,
        daily_stats: pd.DataFrame,
        control_limits: Dict[Tuple[int, str], Dict[str, float]],
    ) -> Path:
        """
        管理図を可視化

        Args:
            pattern_num: 吐出パターン番号
            target_column: ターゲットカラム名
            daily_stats: 日次集計データ
            control_limits: 管理限界の辞書

        Returns:
            保存した画像ファイルのパス
        """
        pattern_data = daily_stats[
            (daily_stats["吐出パターン番号"] == pattern_num)
            & (daily_stats["ターゲットカラム"] == target_column)
        ].sort_values("注入開始日")

        # グラフ表示用に最新PLOT_DAYS日間のみ抽出
        if len(pattern_data) > 0:
            max_date = pattern_data["注入開始日"].max()
            plot_cutoff = max_date - pd.Timedelta(days=PLOT_DAYS - 1)
            pattern_data = pattern_data[pattern_data["注入開始日"] >= plot_cutoff]

        limits = control_limits[(pattern_num, target_column)]
        values = pattern_data["平均"].values

        # 異常判定（全期間で実施：連続性検出のため）
        anomalies = self.check_new_jis_rules(values, limits)

        # 直近DETECTION_DAYS日間の範囲を計算
        max_date = pattern_data["注入開始日"].max()
        detection_cutoff = max_date - pd.Timedelta(days=DETECTION_DAYS - 1)

        # 異常点フラグを直近DETECTION_DAYS日間のみに制限
        # DETECTION_DAYS範囲外のデータポイントは異常フラグをクリア
        anomalies_filtered = []
        for idx, (_, row) in enumerate(pattern_data.iterrows()):
            if row["注入開始日"] >= detection_cutoff:
                anomalies_filtered.append(anomalies[idx])  # 範囲内：異常フラグをそのまま
            else:
                anomalies_filtered.append([])  # 範囲外：異常フラグをクリア
        anomalies = anomalies_filtered

        # 日本語フォントプロパティを設定
        from matplotlib.font_manager import FontProperties

        font_prop = FontProperties(family=self.font_name)

        # プロット
        fig, ax = plt.subplots(figsize=(18, 10))

        # 横軸を日付に設定
        x = pattern_data["注入開始日"].values

        # データ点
        ax.plot(
            x, values, "o-", color="blue", linewidth=2, markersize=6, label="データ点"
        )

        # 管理限界線
        ax.axhline(
            y=limits["CL"],
            color="green",
            linestyle="-",
            linewidth=2,
            label="中心線(CL)",
        )
        ax.axhline(
            y=limits["UCL"], color="red", linestyle="--", linewidth=2, label="UCL (3σ)"
        )
        ax.axhline(
            y=limits["LCL"], color="red", linestyle="--", linewidth=2, label="LCL (3σ)"
        )

        # σ境界線
        ax.axhline(
            y=limits["upper_2sigma"],
            color="orange",
            linestyle=":",
            linewidth=1.5,
            alpha=0.7,
            label="±2σ",
        )
        ax.axhline(
            y=limits["lower_2sigma"],
            color="orange",
            linestyle=":",
            linewidth=1.5,
            alpha=0.7,
        )
        ax.axhline(
            y=limits["upper_1sigma"],
            color="yellow",
            linestyle=":",
            linewidth=1.5,
            alpha=0.7,
            label="±1σ",
        )
        ax.axhline(
            y=limits["lower_1sigma"],
            color="yellow",
            linestyle=":",
            linewidth=1.5,
            alpha=0.7,
        )

        # 異常点を強調
        anomaly_indices = [i for i, a in enumerate(anomalies) if a]
        if anomaly_indices:
            ax.scatter(
                [x[i] for i in anomaly_indices],
                [values[i] for i in anomaly_indices],
                color="red",
                s=200,
                marker="o",
                zorder=5,
                label="異常点",
            )

        # 横軸の日付フォーマット設定
        import matplotlib.dates as mdates
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
        ax.xaxis.set_major_locator(mdates.DayLocator(interval=max(1, len(x) // 10)))
        plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha='right')

        # 軸ラベルとタイトルにフォントを明示的に指定
        ax.set_xlabel(
            "注入開始日", fontsize=14, fontproperties=font_prop
        )
        ax.set_ylabel(f"{target_column}", fontsize=14, fontproperties=font_prop)
        ax.set_title(
            f"新JIS管理図 - 吐出パターン{pattern_num} - {target_column}",
            fontsize=16,
            fontweight="bold",
            fontproperties=font_prop,
        )
        ax.legend(loc="best", fontsize=12, prop=font_prop)
        ax.grid(True, alpha=0.3)

        plt.tight_layout()

        # 保存
        # ファイル名に使用できない文字を置換
        safe_target_name = (
            target_column.replace("/", "_").replace("(", "_").replace(")", "_")
        )
        save_path = (
            self.output_dir
            / "figures"
            / f"control_chart_pattern_{pattern_num}_{safe_target_name}_{self.timestamp}.png"
        )
        plt.savefig(save_path, dpi=300, bbox_inches="tight")
        plt.close()

        self.logger.info(f"管理図保存: {save_path}")

        return save_path

    def run(
        self,
        data_path: str,
        missing_ids_path: str = None,
        control_limits_path: str = None,
        plot_pattern_num: int = None,
    ) -> Tuple[pd.DataFrame, Dict[Tuple[int, str], Dict[str, float]]]:
        """
        Phase 2異常検知を実行

        Args:
            data_path: オリジナルデータのパス
            missing_ids_path: missing_idsファイルのパス（Noneの場合は最新を自動検出）
            control_limits_path: Phase 0管理限界ファイルのパス（Noneの場合は最新を自動検出）
            plot_pattern_num: 可視化する吐出パターン番号（Noneの場合は可視化なし）

        Returns:
            (異常データのDataFrame, 管理限界の辞書)
        """
        # Phase 0の管理限界を読み込み
        phase0_control_limits = self.load_control_limits(control_limits_path)

        # データ読み込み
        df_clean = self.load_clean_data(data_path, missing_ids_path)
        total_clean = len(df_clean)

        # オリジナルデータの行数（参照用）
        df_original = load_data(data_path)
        total_original = len(df_original)

        self.logger.info(
            f"日次集計開始: {len(self.target_columns)}種類のターゲットカラム"
        )

        # 日付範囲の計算（utils.aggregate_dailyで日付変換されるため、先に集計して確認）
        temp_daily_stats = aggregate_daily(df_clean.copy(), self.target_columns[0])
        min_date = temp_daily_stats["注入開始日"].min()
        max_date = temp_daily_stats["注入開始日"].max()
        cutoff_date = max_date - pd.Timedelta(days=DETECTION_DAYS - 1)

        self.logger.info(f"データ期間: {min_date} 〜 {max_date}")
        self.logger.info(
            f"異常判定対象期間（直近{DETECTION_DAYS}日間）: {cutoff_date} 〜 {max_date}"
        )

        # 全ターゲットカラムに対して処理
        all_daily_stats = []
        all_anomalies = []
        all_control_limits = {}

        for target_column in self.target_columns:
            self.logger.info(f"処理中: {target_column}")

            # 日次集計（utils関数を使用）
            daily_stats = aggregate_daily(df_clean, target_column)
            all_daily_stats.append(daily_stats)

            # 異常検知（Phase 0の管理限界を使用）
            anomalies_df, control_limits = self.detect_anomalies(
                daily_stats, target_column, phase0_control_limits
            )
            all_anomalies.append(anomalies_df)
            all_control_limits.update(control_limits)

            self.logger.info(f"  {target_column}: 異常検出数={len(anomalies_df)}件")

        # 全ターゲットカラムの結果を統合
        all_daily_stats_df = pd.concat(all_daily_stats, ignore_index=True)
        all_anomalies_df = pd.concat(all_anomalies, ignore_index=True)

        self.logger.info(
            f"日次集計完了: {all_daily_stats_df.shape[0]}行, 吐出パターン数={all_daily_stats_df['吐出パターン番号'].nunique()}, 日数={all_daily_stats_df['注入開始日'].nunique()}"
        )
        self.logger.info("異常検知開始（新JIS 8つのルール）")
        self.logger.info(f"異常検出完了: {len(all_anomalies_df)}件")

        # ルール別の異常数を集計
        if len(all_anomalies_df) > 0:
            rule_counts = {}
            for rules in all_anomalies_df["違反ルール"]:
                for rule in rules:
                    rule_counts[rule] = rule_counts.get(rule, 0) + 1

            self.logger.info("ルール別異常検出数:")
            for rule_num in sorted(rule_counts.keys()):
                self.logger.info(f"  ルール{rule_num}: {rule_counts[rule_num]}件")

        # 結果保存
        self.save_results(
            all_anomalies_df, all_daily_stats_df, total_original, total_clean
        )

        # 管理図を可視化（特定のパターンが指定された場合のみ）
        if plot_pattern_num is not None:
            self.logger.info(
                f"管理図可視化: 吐出パターン{plot_pattern_num}の全ターゲットカラム"
            )
            for target_column in self.target_columns:
                # 該当データが存在するか確認
                pattern_data = all_daily_stats_df[
                    (all_daily_stats_df["吐出パターン番号"] == plot_pattern_num)
                    & (all_daily_stats_df["ターゲットカラム"] == target_column)
                ]
                if len(pattern_data) > 0:
                    self.plot_control_chart(
                        plot_pattern_num,
                        target_column,
                        all_daily_stats_df,
                        all_control_limits,
                    )

        self.logger.info("Phase 2完了")

        return all_anomalies_df, all_control_limits


def main():
    """メイン処理"""
    # パス設定
    script_dir = Path(__file__).parent
    project_dir = script_dir.parent

    data_path = project_dir / "data" / ANOMALY_DETECTION_FILE
    log_dir = project_dir / "logs"
    output_dir = project_dir / "output"

    print("=" * 80)
    print("Phase 2: X-R管理図による異常検知")
    print("=" * 80)
    print(f"\n対象データ: {ANOMALY_DETECTION_FILE}")
    print("Phase 0の管理限界を使用して異常検知を実行します...")
    print(f"異常判定対象期間: 直近{DETECTION_DAYS}日間のみ\n")

    # Phase 2実行（全ターゲットカラム）
    xr_chart = XRControlChart(
        log_dir=str(log_dir),
        output_dir=str(output_dir),
        target_columns=None,  # 全てのターゲットカラム
    )

    # SAVE_FIGURESフラグがTrueの場合のみ可視化
    plot_pattern = 1 if SAVE_FIGURES else None

    anomalies_df, control_limits = xr_chart.run(
        data_path=str(data_path),
        plot_pattern_num=plot_pattern,  # config.pyのSAVE_FIGURESに従う
    )

    # サマリー表示
    print("\n" + "=" * 80)
    print("Phase 2: 新JIS X-R管理図による異常検知 完了")
    print("=" * 80)
    print(f"異常検出数: {len(anomalies_df)}件")

    if len(anomalies_df) > 0:
        # ターゲットカラム別の異常数
        print("\nターゲットカラム別異常検出数:")
        target_counts = anomalies_df["ターゲットカラム"].value_counts()
        for target, count in target_counts.items():
            print(f"  {target}: {count}件")

        # ルール別の異常数
        rule_counts = {}
        for rules in anomalies_df["違反ルール"]:
            for rule in rules:
                rule_counts[rule] = rule_counts.get(rule, 0) + 1

        print("\nルール別異常検出数:")
        for rule_num in sorted(rule_counts.keys()):
            print(f"  ルール{rule_num}: {rule_counts[rule_num]}件")

    print("=" * 80)


if __name__ == "__main__":
    main()
