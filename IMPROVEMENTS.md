# Strava Training Advisor 改善提案

コードベース全体をレビューした結果、以下の改善点を提案します。

---

## 1. テストの追加（優先度: 高）

現在テストが一切存在しません。リファクタリングやバグ修正の安全性を担保するため、テストの追加が最も重要です。

### 対象モジュールと具体例

**`src/models.py` — ユニットテスト**
- `TrainingZones.classify_hr()` の境界値テスト（Zone 0/1/2/3/4 の各閾値）
- `ZoneDistribution.low_intensity_pct` / `high_intensity_pct` のゼロ除算ケース
- `Activity` の computed properties（`distance_km`, `average_pace_min_per_km` で speed=0 のケース）
- `Race.days_until` / `Race.is_past` の日付境界

**`src/analyzer.py` — ユニットテスト**
- `_compute_zone_distribution()`: ストリームデータあり／なし／心拍データなしの3パターン
- `_check_recovery_week_pattern()`: 回復週パターン検出の正常系・エッジケース（4週未満など）
- `_group_by_week()`: 週跨ぎのグルーピング検証

**`src/race_manager.py` — ユニットテスト**
- トレーニングフェーズ判定（Base/Build/Peak/Taper/Recovery の各境界日数）
- `races.yaml` が存在しない場合のフォールバック

**`src/strava_client.py` — モック統合テスト**
- `requests` をモックしてトークンリフレッシュフローを検証
- ページネーションの動作確認
- エラーレスポンス時のハンドリング

**`src/advisor.py` — モック統合テスト**
- Claude API をモックしてプロンプト構築の正確性を検証

### 推奨構成

```
tests/
├── conftest.py          # 共通フィクスチャ（Activity, TrainingZones のファクトリ）
├── test_models.py
├── test_analyzer.py
├── test_race_manager.py
├── test_strava_client.py
└── test_advisor.py
```

`pyproject.toml` に追加:
```toml
[dependency-groups]
dev = ["pytest>=8.0", "pytest-cov>=6.0", "responses>=0.25"]
```

---

## 2. エラーハンドリングの改善（優先度: 高）

### 2a. サイレントな例外キャッチの修正

**問題箇所:**
- `src/strava_client.py:124` — `except Exception: pass`
- `scripts/check_new_activities.py:85` — `except Exception: pass`

ストリームの取得失敗が完全に無視されており、デバッグが困難です。

**提案:**
```python
# Before
except Exception:
    pass

# After
except requests.RequestException as e:
    logger.warning("ストリーム取得失敗 (activity=%d): %s", activity.id, e)
```

### 2b. logging モジュールの導入

現在 `print()` と `sys.stderr` が混在しています。標準の `logging` モジュールに統一することで、ログレベルの制御やフォーマット統一が可能になります。

```python
import logging

logger = logging.getLogger(__name__)

# 現在: print(f"ERROR: ...", file=sys.stderr)
# 提案: logger.error("Strava APIからのデータ取得に失敗: %s", e)
```

### 2c. Strava API レート制限への対応

Strava API には 15分あたり100リクエスト、1日あたり1000リクエストの制限があります。現在これを一切考慮していません。

**提案:**
- レスポンスヘッダ `X-RateLimit-Limit` / `X-RateLimit-Usage` を監視
- 制限に近づいた場合に `time.sleep()` で待機
- 429 レスポンスに対するリトライ（指数バックオフ）

### 2d. リトライロジックの追加

外部API呼び出し（Strava、Claude、Discord）にリトライロジックがありません。

```python
# tenacity ライブラリ、またはシンプルな自前実装
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, max=10))
def _get(self, path, params=None):
    ...
```

---

## 3. コード品質ツールの導入（優先度: 中）

### 3a. リンター / フォーマッター

`ruff` を導入すれば、linting と formatting を一つのツールで管理できます。

```toml
# pyproject.toml に追加
[tool.ruff]
target-version = "py314"
line-length = 100

[tool.ruff.lint]
select = ["E", "F", "W", "I", "UP", "B", "SIM"]
```

### 3b. 型チェック（mypy）

型ヒントは既に使われていますが、`mypy` による静的チェックが未設定です。`# type: ignore` が複数箇所にあり、型安全性の検証が不十分です。

```toml
[tool.mypy]
python_version = "3.14"
warn_return_any = true
warn_unused_configs = true
disallow_untyped_defs = true
```

### 3c. CI への組み込み

GitHub Actions ワークフローにテスト・リント・型チェックのジョブを追加:

```yaml
# .github/workflows/ci.yml (新規)
name: CI
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v4
      - run: uv sync
      - run: uv run pytest --cov=src
      - run: uv run ruff check .
      - run: uv run mypy src/
```

---

## 4. 設定バリデーションの強化（優先度: 中）

### 4a. 環境変数のバリデーション

起動時に必要な環境変数がすべて設定されているかチェックし、不足時に分かりやすいエラーメッセージを出す仕組みがありません。`advisor.py` は `ANTHROPIC_API_KEY` が未設定のまま API 呼び出しに進み、分かりにくいエラーになります。

**提案:** 起動時バリデーション関数を追加

```python
def validate_config() -> None:
    required = ["STRAVA_CLIENT_ID", "STRAVA_CLIENT_SECRET", "ANTHROPIC_API_KEY"]
    missing = [key for key in required if not os.getenv(key)]
    if missing:
        raise EnvironmentError(f"必須環境変数が未設定: {', '.join(missing)}")
```

### 4b. `races.yaml` のスキーマバリデーション

YAML の構造が不正な場合（型の不一致、必須フィールドの欠落など）にサイレントに失敗する可能性があります。

**提案:** `pydantic` または手動バリデーションでスキーマチェックを追加

---

## 5. アーキテクチャの改善（優先度: 中）

### 5a. `main.py` の整理

`main.py` は現在空の `main()` 関数のみで未使用です。削除するか、CLIエントリポイントとして `run_advisor.py` の内容を統合すべきです。

### 5b. `pyproject.toml` のエントリポイント設定

```toml
[project.scripts]
strava-advisor = "scripts.run_advisor:main"
strava-check = "scripts.check_new_activities:main"
```

これにより `uv run strava-advisor` で直接実行可能になります。

### 5c. `sys.path` の操作を排除

`check_new_activities.py:21` で `sys.path.insert()` を使って親ディレクトリを追加しています。上記のエントリポイント設定により、この hack は不要になります。

---

## 6. GitHub Actions ワークフローの改善（優先度: 中）

### 6a. トークンリフレッシュ問題

GitHub Secrets に保存された `STRAVA_ACCESS_TOKEN` / `STRAVA_REFRESH_TOKEN` は、ワークフロー実行時にリフレッシュされても **Secrets には書き戻されません**。これはトークンの有効期限が切れた後に問題を引き起こす可能性があります。

**提案:**
- GitHub API を使って Secrets を更新するステップを追加
- または、外部のトークンストレージ（例: GitHub Actions の artifact やクラウド KVS）を利用

### 6b. Python バージョンの不一致

`pyproject.toml` では `requires-python = ">=3.14"` ですが、GitHub Actions では `python-version: '3.12'` を使用しています。これは互換性の問題を引き起こす可能性があります。

**提案:** GitHub Actions の Python バージョンを `3.14` に統一

### 6c. ワークフローの stderr 処理

現在の `2>&1` リダイレクトにより、stderr のエラーメッセージと stdout の正常出力が混在しています。

**提案:** stderr と stdout を分離して処理し、エラー時に明確に失敗させる

```yaml
run: |
  uv run python scripts/check_new_activities.py | tee /tmp/output.txt
  NEW_ID=$(grep '^NEW_ACTIVITY_ID=' /tmp/output.txt | cut -d= -f2 || true)
  echo "new_activity_id=$NEW_ID" >> $GITHUB_OUTPUT
```

---

## 7. 機能追加の提案（優先度: 低）

### 7a. アクティビティ単体のゾーン分布表示

Discord 通知に表示されるゾーン分布は **過去12週全体** の集計です。新しいアクティビティ単体のゾーン分布も表示すると、個別のランの評価がより明確になります。

### 7b. 週次サマリー通知

毎週月曜日に過去1週間のトレーニングサマリーを Discord に送信する機能。個別通知だけでなく、週単位の振り返りができます。

### 7c. ペースゾーンの分析

現在は心拍ゾーンのみですが、ペースゾーンの分析を追加することで、心拍計なしのランや心拍計の不具合時にも有用な分析が可能です。

### 7d. トレンドの可視化強化

週次レポートの HTML に以下を追加:
- 低強度割合の推移グラフ（80%ラインとの比較）
- AeT/AnT の変化トラッキング（手動入力ベース）

---

## 8. 依存関係の見直し（優先度: 低）

### 8a. `pandas` の必要性

`pandas` が `pyproject.toml` に含まれていますが、ソースコード内で `import pandas` が見つかりません。実際に使われていない場合は削除すべきです。不要な依存はインストール時間と攻撃面を増加させます。

### 8b. `requires-python = ">=3.14"` の妥当性

Python 3.14 は非常に新しく、多くの環境で利用できません。コードを確認した限り、3.12 でも動作する構文しか使われていません。`>=3.12` に緩和することを推奨します。

---

## 改善の優先順位まとめ

| 順位 | 改善項目 | 影響度 | 工数 |
|------|---------|--------|------|
| 1 | テストの追加 | 高 | 大 |
| 2 | サイレント例外の修正 + logging 導入 | 高 | 小 |
| 3 | Strava API レート制限対応 | 高 | 中 |
| 4 | ruff / mypy 導入 | 中 | 小 |
| 5 | 環境変数・YAML バリデーション | 中 | 小 |
| 6 | GH Actions Python バージョン統一 | 中 | 小 |
| 7 | GH Actions トークンリフレッシュ対応 | 中 | 中 |
| 8 | main.py 整理 + エントリポイント設定 | 中 | 小 |
| 9 | pandas 削除 + requires-python 緩和 | 低 | 小 |
| 10 | 機能追加（単体ゾーン分布、週次サマリー等） | 低 | 大 |
