"""
共通ユーティリティ関数

Phase 0とPhase 2で共通で使用する関数を定義します。
"""

import pandas as pd
from datetime import datetime
from typing import Dict


def excel_serial_to_datetime(serial):
    """
    Excelシリアル値をdatetimeに変換（ロバストな実装）

    Args:
        serial: Excelシリアル値（数値）または文字列

    Returns:
        datetime: 変換後の日時（失敗時はpd.NaT）
    """
    if pd.isna(serial):
        return pd.NaT

    # 既にdatetime型の場合はそのまま返す
    if isinstance(serial, (datetime, pd.Timestamp)):
        return pd.Timestamp(serial)

    # 文字列の場合は数値変換を試みる
    if isinstance(serial, str):
        try:
            serial = float(serial)
        except ValueError:
            # 数値変換失敗時はpd.to_datetimeで文字列として解析
            try:
                return pd.to_datetime(serial, errors="coerce")
            except Exception:
                return pd.NaT

    # Excelシリアル値として変換
    try:
        serial_float = float(serial)
        # Excelシリアル値の妥当な範囲チェック（1899-12-30 ～ 2100-01-01）
        if not (0 <= serial_float <= 73050):  # シリアル値0は1899-12-30
            return pd.NaT

        base_date = datetime(1899, 12, 30)
        return base_date + pd.Timedelta(days=serial_float)
    except (ValueError, TypeError, OverflowError, AttributeError):
        return pd.NaT


def aggregate_daily(df: pd.DataFrame, target_column: str) -> pd.DataFrame:
    """
    吐出パターン毎・日次で集計

    Args:
        df: データフレーム
        target_column: 集計対象の特性値列名

    Returns:
        日次集計データのDataFrame
    """
    # 注入開始日時を変換（常に再生成して最新の状態を保証）
    # 複数のフォーマットとデータ型に対応するロバストな日付処理

    # dtypeの文字列表現で判定（より確実）
    dtype_str = str(df["注入開始日時"].dtype)

    # まず、object型でも数値（Excelシリアル値）かどうかをチェック
    is_numeric_string = False
    if dtype_str in ["object", "str", "string"] or "str" in dtype_str or "object" in dtype_str:
        # サンプルデータで数値変換可能かチェック
        sample_values = df["注入開始日時"].dropna().head(100)
        numeric_count = 0
        for val in sample_values:
            try:
                float(val)
                numeric_count += 1
            except (ValueError, TypeError):
                pass
        # 90%以上が数値変換可能ならExcelシリアル値とみなす
        is_numeric_string = (numeric_count / len(sample_values)) > 0.9 if len(sample_values) > 0 else False

    if is_numeric_string:
        # 文字列だがExcelシリアル値の場合（例: "45901.60227"）
        df["注入開始日時_datetime"] = df["注入開始日時"].apply(
            excel_serial_to_datetime
        )
    elif dtype_str in ["object", "str", "string"] or "str" in dtype_str or "object" in dtype_str:
        # 文字列形式の日付の場合（例: "2025/12/26", "2025-12-26", "2025/12/26 10:30:00"）
        # 複数の日付フォーマットを試行
        df["注入開始日時_datetime"] = pd.to_datetime(
            df["注入開始日時"],
            errors="coerce",
            format="mixed"  # 複数フォーマットに対応
        )

        # まだNaTが多い場合、手動で複数フォーマットを試行
        if df["注入開始日時_datetime"].isna().sum() > len(df) * 0.5:
            # 一般的な日付フォーマットのリスト
            date_formats = [
                "%Y/%m/%d",
                "%Y-%m-%d",
                "%Y/%m/%d %H:%M:%S",
                "%Y-%m-%d %H:%M:%S",
                "%Y年%m月%d日",
                "%m/%d/%Y",
                "%d/%m/%Y"
            ]

            for fmt in date_formats:
                mask = df["注入開始日時_datetime"].isna()
                if mask.sum() == 0:
                    break
                df.loc[mask, "注入開始日時_datetime"] = pd.to_datetime(
                    df.loc[mask, "注入開始日時"],
                    format=fmt,
                    errors="coerce"
                )
    else:
        # 数値型の場合（Excelシリアル値）
        df["注入開始日時_datetime"] = df["注入開始日時"].apply(
            excel_serial_to_datetime
        )

    # dt.dateではなくdt.normalizeを使用してpd.Timestamp型を維持
    df["注入開始日"] = df["注入開始日時_datetime"].dt.normalize()

    # 変換後の検証：NaTが多すぎる場合は警告
    nat_count = df["注入開始日"].isna().sum()
    if nat_count > 0:
        nat_ratio = nat_count / len(df) * 100
        if nat_ratio > 10:
            import warnings
            warnings.warn(
                f"日付変換で{nat_count}行 ({nat_ratio:.1f}%)がNaTになりました。"
                f"元データのフォーマットを確認してください。"
            )

    # 集計
    daily_stats = (
        df.groupby(["吐出パターン番号", "注入開始日"])[target_column]
        .agg(
            [
                ("平均", "mean"),
                ("標準偏差", "std"),
                ("最小", "min"),
                ("最大", "max"),
                ("サンプル数", "count"),
            ]
        )
        .reset_index()
    )

    # 範囲（R）を計算
    daily_stats["範囲_R"] = daily_stats["最大"] - daily_stats["最小"]

    # ターゲットカラム名を記録
    daily_stats["ターゲットカラム"] = target_column

    return daily_stats


def calculate_control_limits(
    pattern_data: pd.DataFrame, d2_table: Dict[int, float]
) -> Dict[str, float]:
    """
    管理限界を計算

    Args:
        pattern_data: 特定の吐出パターンのデータ
        d2_table: d2係数テーブル

    Returns:
        管理限界の辞書
    """
    # X̄（全体平均）
    x_double_bar = pattern_data["平均"].mean()

    # R̄（範囲の平均）
    r_bar = pattern_data["範囲_R"].mean()

    # σの推定値（R̄/d2を使用）
    n = int(pattern_data["サンプル数"].median())
    d2 = d2_table.get(min(n, 10), 2.059)
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
        "CL": float(x_double_bar),
        "UCL": float(ucl),
        "LCL": float(lcl),
        "sigma": float(sigma),
        "upper_2sigma": float(upper_2sigma),
        "upper_1sigma": float(upper_1sigma),
        "lower_1sigma": float(lower_1sigma),
        "lower_2sigma": float(lower_2sigma),
        "n": int(n),
        "d2": float(d2),
    }
