# Strava Training Advisor

StravaのランニングデータをAIが分析し、[Uphill Athlete](https://uphillathlete.com/)のトレーニング哲学に基づいてコーチングアドバイスを生成するツールです。新しいランを記録するとDiscordに自動通知が届き、毎週日曜夜には週次サマリーと来週の目標が送信されます。**筋トレアクティビティも自動取得し、頻度リマインダーも提供します。**

---

## システムの仕組み

```
┌─────────────────────────────────────────────────────────┐
│  GitHub Actions（自動実行）                               │
│                                                         │
│  【10分毎】新着アクティビティ検知                           │
│  1. Strava API をポーリング                               │
│     └─ 最新アクティビティIDを確認                          │
│                                                         │
│  2. 新しいアクティビティを検知した場合:                       │
│     a. 過去12週のデータ＋心拍ストリームを取得               │
│     b. Uphill Athlete Z0-Z4で分析（ADS診断含む）           │
│     c. 筋トレは専用通知、ランは詳細分析                      │
│     d. Claude AI がアドバイスを生成                        │
│     e. Discord に通知（心拍ドリフト・ゾーン分布含む）        │
│     f. .last_activity_id を更新（自動 git commit）          │
│                                                         │
│  【毎週日曜 JST 20:00】週次サマリー                        │
│  1. 今週の実績を集計（距離・時間・ゾーン分布）               │
│  2. 3:1サイクル・ADS診断                                  │
│  3. Claude AI が来週の目標スケジュールを生成                │
│  4. Discord に週次サマリー送信                             │
└─────────────────────────────────────────────────────────┘
         ↓ ポーリング          ↓ 通知
    Strava API            Discord Webhook
```

### GitHub Actionsから定期実行しているのですか？

**はい。** `.github/workflows/strava-monitor.yml` に記述されたスケジュール（10分毎 + 毎週日曜JST 20:00）でGitHubのサーバーが自動的にスクリプトを実行します。自分のMacが起動していなくても動き続けます。

### 新着の検知方法

WebhookではなくPolling（ポーリング）方式です。

- `.last_activity_id` ファイル（リポジトリにgit管理）に保存された最後のアクティビティIDと、Strava APIから取得した最新IDを比較
- IDが変わっていれば新しいランと判断して分析・通知
- 新着が検出されると、ワークフローが自動的に `.last_activity_id` を更新してgit commit・push
- 同じなら何もしない（APIコールのみで終了）

### コストはかかりますか？

| サービス | コスト |
|---|---|
| **GitHub Actions** | **無料**（公開リポジトリは実行時間無制限） |
| **Strava API** | **無料**（個人利用の範囲） |
| **Discord Webhook** | **無料** |
| **Claude API (Anthropic)** | **新着ランがあった時 + 週1回課金** |

Claude APIのコストは、新しいランを記録するたびに1回 + 毎週日曜のサマリーで1回発生します。1回あたりの目安は **約0.5〜1円**。月20回走っても **約30〜40円程度** です。

---

## ファイル構成

```
strava-training-advisor/
├── races.yaml                        # レース予定（自分で編集）
├── athlete_profile.yaml              # アスリートプロファイル（自分で編集・任意）
├── .last_activity_id                 # 最後に検出したアクティビティID（git管理・自動更新）
├── .env                              # APIキー等（git管理外）
├── .env.example                      # .envのテンプレート
├── pyproject.toml                    # 依存パッケージ定義
│
├── src/
│   ├── models.py                     # データ構造の定義（Z0対応・筋トレ対応）
│   ├── strava_client.py              # Strava API クライアント（ランニング＋筋トレ取得）
│   ├── analyzer.py                   # Uphill Athlete Z0-Z4分析（正規分布フォールバック・JST基準）
│   ├── advisor.py                    # Claude AI によるアドバイス生成（ADS診断・筋トレ対応）
│   ├── athlete_profile.py            # アスリートプロファイルの読み込みとフォーマット
│   ├── race_manager.py               # レース予定の読み込みとフェーズ判定（JST基準）
│   ├── notifier.py                   # Discord Webhook 通知（ラン詳細・筋トレ・週次サマリー）
│   └── report.py                     # HTML レポート生成（Z0-Z4グラフ・手動実行用）
│
├── scripts/
│   ├── setup_oauth.py                # Strava OAuth2 初回認証（初回のみ）
│   ├── run_advisor.py                # 手動でレポートを生成・表示
│   ├── check_new_activities.py       # GitHub Actions から呼ばれる新着チェック
│   └── weekly_summary.py             # 毎週日曜 JST 20:00 に実行される週次サマリー生成
│
└── .github/
    └── workflows/
        └── strava-monitor.yml        # GitHub Actions ワークフロー定義
```

---

## Uphill Athlete トレーニング哲学

このツールは以下の原則に基づいて分析・アドバイスを行います。

### Z0-Z4 5ゾーンシステム（心拍数ベース）

| ゾーン | 心拍範囲 | 強度 | 目的 |
|---|---|---|---|
| Zone 0 | AeT × 80% 未満 | 超低強度 | ウォームアップ・下り歩き・回復 |
| Zone 1 | AeT × 80〜90% | 非常に楽 | 回復・基礎有酸素・脂肪代謝 |
| Zone 2 | AeT × 90〜100% | 楽〜中程度 | 有酸素ベース構築（主要ゾーン） |
| Zone 3 | AeT〜AnT | 中〜ハード | 乳酸閾値トレーニング |
| Zone 4 | AnT〜最大心拍 | 非常にハード | 無酸素・最大有酸素パワー |

- **AeT**（有酸素閾値）: `.env` の `ATHLETE_AET_HR` に設定
- **AnT**（無酸素閾値）: `.env` の `ATHLETE_ANT_HR` に設定
- **85/15ルール**: トレーニング時間の85%以上をZone 0-1-2で行う（UAの正確な推奨値）
- **Z0の重要性**: トレイルランではウォームアップ・下り・歩きでZ0に入る時間が多い。Z0を分母に含めることで、Z3比率の過大表示を防ぎ正確な強度分布を把握できる

### ADS診断（10%テスト）

AeT/AnT差（= (AnT - AeT) / AnT × 100）で有酸素不全症候群（ADS）を判定します。

| 差 | 判定 | 対応 |
|---|---|---|
| > 10% | ADS疑い | Zone 3/4禁止、有酸素ベース徹底強化 |
| ≤ 10% | 正常 | 高強度トレーニング5〜10%まで導入可 |

### UA 3本柱

Uphill Athlete では以下の3本柱をバランスよく鍛えることを推奨します。

1. **有酸素ベース**: Z0-Z2中心のランニングで毛細血管・ミトコンドリアを発達させる
2. **筋力**: スクワット・ランジ・コアワークなど週2回の一般的筋力トレーニング
3. **特異的持久力（ME）**: ヒルリピートなど競技特異的な筋持久力

このツールは筋トレも Strava から自動取得し、週2回の目標に対して達成状況をDiscordでリマインドします。

### 3大原則

- **継続性**: 一貫したトレーニングが最大の適応をもたらす
- **段階性**: 初心者は年25%増可、上級者は10%以下（週10%ルール）
- **変調**: 3週構築 + 1週回復（最困難週の50%に削減）

### トレーニングフェーズ（Aレースまでの日数で自動判定）

| フェーズ | 時期 | 低強度目標 | 内容 |
|---|---|---|---|
| Base | 12週以上前 | Z0+Z1+Z2: **90%以上** | 有酸素ベース中心、Z3原則禁止 |
| Build | 8〜12週前 | Z0+Z1+Z2: **85%以上** | ボリューム増加、ME週1回、Z3週1回まで |
| Peak | 4〜8週前 | Z0+Z1+Z2: **80%以上** | 最大負荷、ME週1〜2回、30/30週1回 |
| Taper | 4週前以内 | — | ボリューム40〜60%削減、強度維持 |
| Recovery | Aレース直後2週 | Z0+Z1のみ | 完全回復優先、Z2以上禁止 |

### 心拍ドリフト分析

アクティビティ内の後半・前半の平均心拍を比較し、有酸素ベースの強さを評価します。

| ドリフト | 評価 |
|---|---|
| ≤ 3% | ✅ 良好（AeT以下で安定） |
| 3〜5% | ⚠️ 注意 |
| 5〜10% | ⚠️ 有酸素ベース不足の可能性 |
| > 10% | 🔴 深刻（強度過多） |

---

## セットアップ

### 必要なもの

- GitHubアカウント（公開リポジトリ）
- Stravaアカウント + APIアプリ登録
- Anthropic APIキー
- Discordサーバー（通知先チャンネル）

### 手順

**1. Strava APIアプリを登録**

1. https://www.strava.com/settings/api にアクセス
2. アプリを作成（Authorization Callback Domain: `localhost`）
3. Client ID と Client Secret を控える

**2. ローカルでOAuth認証（初回のみ）**

```bash
cp .env.example .env
# .envを編集してSTRAVA_CLIENT_ID, STRAVA_CLIENT_SECRET, ANTHROPIC_API_KEY, AeT/AnT心拍数を入力

uv run python scripts/setup_oauth.py
# ブラウザが開くので「許可」→ .envにトークンが自動保存される
```

**3. GitHubにpush**

```bash
git remote set-url origin https://github.com/YOUR_USERNAME/strava-training-advisor.git
git push -u origin main
```

**4. GitHub Secrets を設定**

リポジトリ → Settings → Secrets and variables → Actions → **Repository secrets** に追加：

| Secret名 | 値 |
|---|---|
| `STRAVA_CLIENT_ID` | StravaのClient ID |
| `STRAVA_CLIENT_SECRET` | StravaのClient Secret |
| `STRAVA_ACCESS_TOKEN` | `.env`の値 |
| `STRAVA_REFRESH_TOKEN` | `.env`の値 |
| `STRAVA_TOKEN_EXPIRES_AT` | `.env`の値 |
| `ANTHROPIC_API_KEY` | AnthropicのAPIキー |
| `DISCORD_WEBHOOK_URL` | DiscordのWebhook URL |
| `ATHLETE_AET_HR` | 有酸素閾値心拍数（例: 135） |
| `ATHLETE_ANT_HR` | 無酸素閾値心拍数（例: 155） |

**5. Discord Webhook を作成**

通知したいチャンネル → 歯車アイコン → 連携サービス → ウェブフック → 新しいウェブフック → URLをコピー

**6. 動作確認**

Actions タブ → "Strava Activity Monitor" → "Run workflow" で手動実行

---

## アスリートプロファイルの設定（任意）

`athlete_profile.yaml` を編集することで、AIアドバイスをより個人化できます。

```yaml
schedule:
  weekday_pattern: "平日はなるべくジョグ（easy run）。週1回スピードセッション"
  weekend_pattern: "週末にロング走。できればトレイルで"
  strength_training:
    target_per_week: 2          # 週の筋トレ目標回数
    notes: "忘れがちなのでリマインダー必要"

preferences:
  terrain: "trail"              # trail / road / mixed
  weekly_build_rate_max: 10     # 週間距離の最大増加率（%）
  recovery_week_interval: 4     # N週ごとに回復週を入れる

goals:
  primary: "信越五岳100マイル（トレイルウルトラ）"
  secondary: "東京マラソン完走"
  weaknesses:
    - "筋トレを忘れがち"
    - "トレイルの登りで意図せず Z3 に入りがち"
```

このファイルがなくても動作します（後方互換）。

---

## レース予定の管理

`races.yaml` を直接編集します。

```yaml
races:
  - name: 信越五岳100マイル
    date: 2026-09-20
    priority: A      # A=最重要, B=重要, C=参加程度
    distance_km: 160
    notes: 年間最大目標レース

  - name: ハセツネ30K
    date: 2026-03-30
    priority: C
    distance_km: 30
    notes: テストレース
```

編集後は `git add races.yaml && git commit -m "update races" && git push` でGitHubに反映します。

---

## 手動でHTMLレポートを生成

```bash
uv run python scripts/run_advisor.py --open
```

過去12週のデータを分析したHTMLレポートが `results/` フォルダに生成され、ブラウザで開きます。

---

## 週次サマリーを手動で送信

```bash
uv run python scripts/weekly_summary.py
```

または、GitHub Actions の "Run workflow" から `run_weekly_summary=true` を指定して実行できます。

---

## AeT（有酸素閾値）の測定方法

Uphill Athleteの「心拍ドリフトテスト」で測定できます。

1. 一定ペースで60分ラン（前半30分と後半30分の平均心拍を比較）
2. 心拍が5%以上上昇していれば、そのペースはAeT以上
3. 心拍が安定する最大ペースの心拍数がAeT

詳細: https://uphillathlete.com/aerobic-training/heart-rate-drift-test/

---

## 変更履歴

### v3.0（2026-04）

**Z3過大表示バグの修正（重要）**
- `ZoneDistribution.total_s` が Z0（AeT×80%未満）を除外していた問題を修正
- 修正前: 平均HR が AeT 以下でも Z3 が 33% と表示されることがあった
- 修正後: Z0 を分母に含めることでトレイルラン特有の下り・歩き時間を正しく計上
- フォールバック推定を正規分布ベースに改善（平均HRから全時間を1ゾーンに割り当てる旧ロジックを廃止）

**筋トレアクティビティの取り込み**
- Strava の WeightTraining / Workout / Crossfit / Yoga を自動取得
- 週次の筋トレ回数を集計し、目標（週2回）に対してDiscord通知でリマインド
- 筋トレアクティビティには専用の Discord 通知フォーマット

**Z0-Z4 5ゾーン表示**
- ゾーン表示・チャート・Discord通知すべてに Z0 を追加
- 低強度目標を 80% → **85%** に修正（UA の正確な推奨値）

**個別アクティビティ分析**
- 心拍ストリームから1アクティビティごとのゾーン分布を計算
- アクティビティを自動分類: easy / long_run / tempo / speed / recovery / mixed
- Discord通知でこのランの分類とゾーン内訳を表示

**週次ビルド率の監視**
- 前週比の走行距離増加率を計算し、10%ルール超過を⚠️表示
- 4週に1回の回復週パターンも検出

**アスリートプロファイル対応**
- `athlete_profile.yaml` で練習パターン・目標・弱点を設定
- AIアドバイスの個人化精度が向上

**UAメソッドのアドバイス改善**
- トレイルランナー向けZ3解釈を追加（登りのZ3スパイクは自然・問題ではない）
- 筋力トレーニングの重要性（UA3本柱の1つ）をシステムプロンプトに追加
- フェーズ別の低強度目標を明記（Base 90%+, Build 85%+, Peak 80%+）

### v2.0（2026-03）

**週次サマリー通知**
- 毎週日曜 JST 20:00 に自動送信
- その週の実績（距離・時間・ゾーン分布）を振り返り
- AIが来週の目標距離・時間と月〜日の具体スケジュールを提案

**心拍ストリーム活用**
- アクティビティ内の心拍推移（ドリフト）を分析
- 後半/前半の心拍比較でAeT以上かどうかを自動判定
- Discord通知とAIアドバイス両方に反映

**Uphill Athlete理論の強化**
- ADS（有酸素不全症候群）診断：AeT/AnT差の10%テスト
- 継続性・段階性・変調の3原則をアドバイスに統合
- フェーズ別詳細指針（Base/Build/Peak/Taper/Recovery）
- 筋持久力（ME）トレーニングと30/30インターバルの推奨
- AeT測定ガイド（心拍ドリフトテスト）の提示

**日本時間（JST）統一**
- 全処理をJST基準に統一（旧来はUTC混在）
- 週の区切り・フェーズ判定・アクティビティ分類すべてJST

### v1.0（2025-xx）

- Strava APIポーリングによる新着アクティビティ検知
- Uphill Athlete 4ゾーン分析
- Claude AI によるトレーニングアドバイス生成
- Discord Webhook 通知
- レース予定と自動フェーズ判定
