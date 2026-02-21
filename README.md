# Strava Training Advisor

Stravaのランニングデータを取得し、[Uphill Athlete](https://uphillathlete.com/)のトレーニング哲学に基づいてAIがアドバイスを生成するツールです。新しいランを記録するとDiscordに自動通知が届きます。

---

## システムの仕組み

```
┌─────────────────────────────────────────────────────────┐
│  GitHub Actions（10分毎に自動実行）                       │
│                                                         │
│  1. Strava API をポーリング                               │
│     └─ 最新アクティビティIDを確認                          │
│                                                         │
│  2. 新しいランを検知した場合のみ:                           │
│     a. 過去12週のデータを取得                              │
│     b. Uphill Athlete 4ゾーンで分析                       │
│     c. Claude AI がアドバイスを生成                        │
│     d. Discord に通知                                    │
│     e. LAST_ACTIVITY_ID を更新                           │
└─────────────────────────────────────────────────────────┘
         ↓ ポーリング          ↓ 通知
    Strava API            Discord Webhook
```

### GitHub Actionsから定期実行しているのですか？

**はい。** `.github/workflows/strava-monitor.yml` に記述されたスケジュール（10分毎）でGitHubのサーバーが自動的にスクリプトを実行します。自分のMacが起動していなくても動き続けます。

### 新着の検知方法

WebhookではなくPolling（ポーリング）方式です。

- `LAST_ACTIVITY_ID`（GitHub Variables に保存）と、Strava APIから取得した最新IDを比較
- IDが変わっていれば新しいランと判断して分析・通知
- 同じなら何もしない（APIコールのみで終了）

### コストはかかりますか？

| サービス | コスト |
|---|---|
| **GitHub Actions** | **無料**（公開リポジトリは実行時間無制限） |
| **Strava API** | **無料**（個人利用の範囲） |
| **Discord Webhook** | **無料** |
| **Claude API (Anthropic)** | **新着ランがあった時のみ課金** |

Claude APIのコストは、新しいランを記録するたびに1回発生します。1回あたりの目安は **約0.5〜1円**（入力約1,000トークン + 出力約400トークン、claude-sonnet-4-6の料金）。月20回走っても **約10〜20円程度** です。

---

## ファイル構成

```
strava-training-advisor/
├── races.yaml                        # レース予定（自分で編集）
├── .env                              # APIキー等（git管理外）
├── .env.example                      # .envのテンプレート
├── pyproject.toml                    # 依存パッケージ定義
│
├── src/
│   ├── models.py                     # データ構造の定義
│   ├── strava_client.py              # Strava API クライアント（OAuth2・自動トークンリフレッシュ）
│   ├── analyzer.py                   # Uphill Athlete 4ゾーン分析
│   ├── advisor.py                    # Claude AI によるアドバイス生成
│   ├── race_manager.py               # レース予定の読み込みとフェーズ判定
│   ├── notifier.py                   # Discord Webhook 通知
│   └── report.py                     # HTML レポート生成（手動実行用）
│
├── scripts/
│   ├── setup_oauth.py                # Strava OAuth2 初回認証（初回のみ）
│   ├── run_advisor.py                # 手動でレポートを生成・表示
│   └── check_new_activities.py       # GitHub Actions から呼ばれる新着チェック
│
└── .github/
    └── workflows/
        └── strava-monitor.yml        # GitHub Actions ワークフロー定義
```

---

## Uphill Athlete トレーニング哲学

このツールは以下の原則に基づいて分析・アドバイスを行います。

**4ゾーンシステム（心拍数ベース）**

| ゾーン | 心拍範囲 | 強度 | 目的 |
|---|---|---|---|
| Zone 1 | AeT × 80〜90% | 非常に楽 | 回復・基礎有酸素 |
| Zone 2 | AeT × 90〜100% | 楽〜中程度 | 有酸素ベース構築（主要ゾーン） |
| Zone 3 | AeT〜AnT | 中〜ハード | 乳酸閾値トレーニング |
| Zone 4 | AnT〜最大心拍 | 非常にハード | 無酸素・スピード |

- **AeT**（有酸素閾値）: `.env` の `ATHLETE_AET_HR` に設定
- **AnT**（無酸素閾値）: `.env` の `ATHLETE_ANT_HR` に設定
- **80/20ルール**: トレーニング時間の80%以上をZone 1-2で行う
- **周期化**: 3週間の負荷増加 + 1週間の回復（ピーク週の50%）

**トレーニングフェーズ（Aレースまでの日数で自動判定）**

| フェーズ | 時期 | 内容 |
|---|---|---|
| Base | 12週以上前 | 有酸素ベース中心、Z1-Z2 90%以上 |
| Build | 8〜12週前 | ボリューム増加、週1回Z3セッション |
| Peak | 4〜8週前 | 最大負荷 |
| Taper | 4週前以内 | ボリューム削減、強度維持 |
| Recovery | Aレース直後2週 | 完全回復優先 |

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

**5. GitHub Variables を設定**

同じページの **Variables** タブに追加：

| Variable名 | 値 |
|---|---|
| `LAST_ACTIVITY_ID` | `0` |

**6. Discord Webhook を作成**

通知したいチャンネル → 歯車アイコン → 連携サービス → ウェブフック → 新しいウェブフック → URLをコピー

**7. 動作確認**

Actions タブ → "Strava Activity Monitor" → "Run workflow" で手動実行

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

## AeT（有酸素閾値）の測定方法

Uphill Athleteの「心拍ドリフトテスト」で測定できます。

1. 一定ペースで60分ラン（前半30分と後半30分の平均心拍を比較）
2. 心拍が5%以上上昇していれば、そのペースはAeT以上
3. 心拍が安定する最大ペースの心拍数がAeT

詳細: https://uphillathlete.com/aerobic-training/heart-rate-drift-test/
