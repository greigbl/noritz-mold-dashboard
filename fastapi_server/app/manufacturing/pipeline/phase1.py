"""
フェーズ1: データバリデーション
欠損値がある行をフラグ立てしてログに残す
欠損行のIDを保存して再現可能にする
"""

import pandas as pd
import logging
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

from app.manufacturing.pipeline.config import ANOMALY_DETECTION_FILE, PHASE1_MISSING_IDS_JSON, PHASE1_MISSING_IDS_CSV


class DataValidator:
    """データバリデーションクラス"""

    def __init__(self, log_dir: str = "../logs", output_dir: str = "../output"):
        """
        初期化

        Args:
            log_dir: ログファイル保存ディレクトリ
            output_dir: 出力ファイル保存ディレクトリ
        """
        self.log_dir = Path(log_dir)
        self.output_dir = Path(output_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_file = None
        self._setup_logger()

    def _setup_logger(self):
        """ロガーのセットアップ"""
        self.log_file = self.log_dir / f"phase1_validation_{self.timestamp}.log"

        # ロガーの設定
        self.logger = logging.getLogger("Phase1")
        self.logger.setLevel(logging.INFO)
        self.logger.handlers.clear()

        # ファイルハンドラ
        file_handler = logging.FileHandler(self.log_file, encoding="utf-8")
        file_handler.setLevel(logging.INFO)

        # フォーマッタ
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        file_handler.setFormatter(formatter)
        self.logger.addHandler(file_handler)

    def validate(
        self, df: pd.DataFrame, data_path: str = None
    ) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        データバリデーション実行

        Args:
            df: 検証対象のデータフレーム
            data_path: データパス（ログ用）

        Returns:
            (valid_df, invalid_df): 正常データと異常データのタプル
        """
        self.logger.info("=" * 80)
        self.logger.info("Phase 1: データバリデーション")
        self.logger.info("=" * 80)

        if data_path:
            self.logger.info(f"データパス: {data_path}")

        self.logger.info(f"総行数: {len(df)}")
        self.logger.info(f"総列数: {len(df.columns)}")
        self.logger.info("")

        # 欠損値統計
        total_cells = df.shape[0] * df.shape[1]
        total_missing = df.isnull().sum().sum()
        missing_rate = (total_missing / total_cells) * 100

        self.logger.info("欠損値サマリー:")
        self.logger.info(f"  総セル数: {total_cells:,}")
        self.logger.info(f"  総欠損値数: {total_missing:,}")
        self.logger.info(f"  欠損率: {missing_rate:.2f}%")
        self.logger.info("")

        # 欠損値チェック
        missing_mask = df.isnull().any(axis=1)
        invalid_df = df[missing_mask].copy()
        valid_df = df[~missing_mask].copy()

        rows_missing_rate = (len(invalid_df) / len(df) * 100) if len(df) > 0 else 0

        self.logger.info(
            f"欠損を含む行数: {len(invalid_df)} ({rows_missing_rate:.2f}%)"
        )
        self.logger.info(
            f"完全な行数: {len(valid_df)} ({100 - rows_missing_rate:.2f}%)"
        )
        self.logger.info("")

        # 列ごとの欠損数を記録
        if len(invalid_df) > 0:
            missing_per_column = invalid_df.isnull().sum()
            missing_per_column = missing_per_column[missing_per_column > 0].sort_values(
                ascending=False
            )

            self.logger.info("列ごとの欠損数:")
            for col, count in missing_per_column.items():
                rate = (count / len(df)) * 100
                self.logger.info(f"  - {col}: {count}件 ({rate:.2f}%)")
            self.logger.info("")

            # 欠損行の詳細情報を抽出
            missing_details = self._extract_missing_details(df, invalid_df)

            # 欠損行の詳細 (最初の20件)
            self.logger.info("欠損行の詳細 (最初の20件):")
            for i, detail in enumerate(missing_details[:20], 1):
                self.logger.info(
                    f"  {i}. インデックス={detail['index']}, "
                    f"欠損列数={detail['missing_count']}, "
                    f"欠損列={detail['missing_columns']}"
                )

            if len(missing_details) > 20:
                self.logger.info(f"  ... 他 {len(missing_details) - 20} 件")
            self.logger.info("")

        return valid_df, invalid_df

    def _extract_missing_details(
        self, df: pd.DataFrame, invalid_df: pd.DataFrame
    ) -> List[Dict]:
        """
        欠損行の詳細情報を抽出

        Args:
            df: 元データ
            invalid_df: 欠損を含むデータ

        Returns:
            欠損詳細情報のリスト
        """
        missing_details = []

        for idx in invalid_df.index:
            row = df.loc[idx]
            missing_cols = row[row.isnull()].index.tolist()

            detail = {
                "index": int(idx),
                "missing_columns": missing_cols,
                "missing_count": len(missing_cols),
            }

            # 識別情報があれば追加（NumPy型をPythonネイティブ型に変換）
            id_columns = ["パレットNo", "セット位置", "製品コード"]
            for col in id_columns:
                if col in df.columns and pd.notna(row[col]):
                    value = row[col]
                    if hasattr(value, "item"):  # NumPy型の場合
                        detail[col] = value.item()
                    else:
                        detail[col] = str(value)

            missing_details.append(detail)

        return missing_details

    def save_missing_ids(
        self, df: pd.DataFrame, invalid_df: pd.DataFrame
    ) -> Tuple[Path, Path]:
        """
        欠損行のIDを保存（再現可能にする）

        Args:
            df: 元データ
            invalid_df: 欠損を含むデータ

        Returns:
            (json_path, csv_path): 保存したファイルパスのタプル
        """
        reports_dir = self.output_dir / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)

        # 欠損インデックスと詳細情報を抽出
        missing_indices = invalid_df.index.tolist()
        missing_details = self._extract_missing_details(df, invalid_df)

        rows_missing_rate = (len(invalid_df) / len(df) * 100) if len(df) > 0 else 0

        # JSONデータ作成
        missing_ids_data = {
            "timestamp": self.timestamp,
            "total_rows": len(df),
            "missing_rows_count": len(invalid_df),
            "missing_rate": f"{rows_missing_rate:.2f}%",
            "missing_indices": missing_indices,
            "missing_details": missing_details,
        }

        # JSON保存（上書き保存）
        json_path = reports_dir / PHASE1_MISSING_IDS_JSON
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(missing_ids_data, f, ensure_ascii=False, indent=2)

        self.logger.info("出力ファイル:")
        self.logger.info(f"  - 欠損ID (JSON): {json_path}")

        # CSV保存（簡易版、上書き保存）
        csv_path = None
        if len(missing_details) > 0:
            missing_ids_df = pd.DataFrame(missing_details)
            csv_path = reports_dir / PHASE1_MISSING_IDS_CSV
            missing_ids_df.to_csv(csv_path, index=False, encoding="utf-8-sig")
            self.logger.info(f"  - 欠損ID (CSV): {csv_path}")

        return json_path, csv_path

    def save_validation_report(
        self,
        df: pd.DataFrame,
        valid_df: pd.DataFrame,
        invalid_df: pd.DataFrame,
        data_path: str = None,
    ):
        """
        バリデーションレポートを保存

        Args:
            df: 元データ
            valid_df: 正常データ
            invalid_df: 異常データ
            data_path: データパス（レポート用）
        """
        output_path = self.output_dir / "reports"
        output_path.mkdir(parents=True, exist_ok=True)

        # 欠損IDの保存
        json_path, csv_path = self.save_missing_ids(df, invalid_df)
        self.logger.info("")

        # サマリーレポート作成（上書き保存）
        summary_path = output_path / "phase1_summary.txt"
        total_cells = df.shape[0] * df.shape[1]
        total_missing = df.isnull().sum().sum()
        missing_rate = (total_missing / total_cells) * 100
        rows_missing_rate = (len(invalid_df) / len(df) * 100) if len(df) > 0 else 0

        with open(summary_path, "w", encoding="utf-8") as f:
            f.write("=" * 80 + "\n")
            f.write("Phase 1: データバリデーション サマリーレポート\n")
            f.write("=" * 80 + "\n\n")
            f.write(f"実行日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            if data_path:
                f.write(f"データパス: {data_path}\n\n")

            f.write("データ概要:\n")
            f.write(f"  総行数: {len(df):,}\n")
            f.write(f"  総列数: {len(df.columns)}\n")
            f.write(f"  総セル数: {total_cells:,}\n\n")

            f.write("欠損値統計:\n")
            f.write(f"  総欠損値数: {total_missing:,}\n")
            f.write(f"  欠損率: {missing_rate:.2f}%\n")
            f.write(
                f"  欠損を含む行数: {len(invalid_df):,} ({rows_missing_rate:.2f}%)\n"
            )
            f.write(
                f"  完全な行数: {len(valid_df):,} ({100 - rows_missing_rate:.2f}%)\n\n"
            )

            if len(invalid_df) > 0:
                f.write("列ごとの欠損数:\n")
                missing_per_column = invalid_df.isnull().sum()
                missing_per_column = missing_per_column[
                    missing_per_column > 0
                ].sort_values(ascending=False)
                for col, count in missing_per_column.items():
                    rate = (count / len(df)) * 100
                    f.write(f"  - {col}: {count}件 ({rate:.2f}%)\n")
                f.write("\n")

            f.write("出力ファイル:\n")
            f.write(f"  - ログ: {self.log_file}\n")
            f.write(f"  - 欠損ID (JSON): {json_path}\n")
            if csv_path:
                f.write(f"  - 欠損ID (CSV): {csv_path}\n")
            f.write("\n")
            f.write("次フェーズへ:\n")
            f.write(
                f"  Phase 2で処理する正常データ: {len(valid_df):,}行 ({len(valid_df)/len(df)*100:.2f}%)\n"
            )
            f.write("  ※ missing_idsを参照してオリジナルデータから抽出してください\n")

        # 完了ログ
        self.logger.info("=" * 80)
        self.logger.info("Phase 1 完了")
        self.logger.info("=" * 80)

        print(f"\n✓ サマリーレポートを保存: {summary_path}")
        print(f"✓ ログファイルを保存: {self.log_file}")


def load_data(data_path: str) -> pd.DataFrame:
    """
    データ読み込み（エンコーディング自動判定）

    Args:
        data_path: データファイルパス

    Returns:
        データフレーム
    """
    # 必須列名で妥当性を検証
    required_columns = {"パレットNo", "セット位置"}
    encodings = ["cp932", "shift-jis", "utf-8-sig", "utf-8"]

    df = None
    selected_encoding = None

    for encoding in encodings:
        try:
            candidate_df = pd.read_csv(data_path, encoding=encoding)

            # 必須列がそろっていれば採用
            if required_columns.issubset(set(candidate_df.columns)):
                df = candidate_df
                selected_encoding = encoding
                print(f"✓ エンコーディング '{encoding}' で読み込み成功（列名検証OK）")
                break

        except (UnicodeDecodeError, Exception):
            continue

    if df is None:
        raise ValueError("データの読み込みに失敗しました")

    print(f"\n採用エンコーディング: {selected_encoding}")
    print(f"データ形状: {df.shape}")
    print(f"行数: {len(df):,}")
    print(f"列数: {len(df.columns)}")

    return df


def main():
    """メイン処理"""
    # スクリプトの場所を基準にパスを解決
    script_dir = Path(__file__).parent
    project_dir = script_dir.parent
    data_path = project_dir / "data" / ANOMALY_DETECTION_FILE

    print("=" * 80)
    print("Phase 1: データバリデーション")
    print("=" * 80)
    print(f"\n対象データ: {ANOMALY_DETECTION_FILE}")
    print("データ読み込み中...")

    # データ読み込み
    df = load_data(str(data_path))

    # データバリデーション実行
    log_dir = project_dir / "logs"
    output_dir = project_dir / "output"
    validator = DataValidator(log_dir=str(log_dir), output_dir=str(output_dir))
    valid_df, invalid_df = validator.validate(df, data_path=str(data_path))

    # レポート保存
    validator.save_validation_report(df, valid_df, invalid_df, data_path=str(data_path))

    # 結果表示
    print("\n" + "=" * 80)
    print("Phase 1: データバリデーション 完了")
    print("=" * 80)
    print(f"元データ: {len(df):,}行")
    print(f"欠損行: {len(invalid_df):,}行 ({len(invalid_df)/len(df)*100:.2f}%)")
    print(f"正常データ: {len(valid_df):,}行 ({len(valid_df)/len(df)*100:.2f}%)")
    print("=" * 80)

    return valid_df, invalid_df


if __name__ == "__main__":
    valid_data, invalid_data = main()
