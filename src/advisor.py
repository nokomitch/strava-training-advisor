"""AI training advice generation using Claude API."""

import os

import anthropic
from dotenv import load_dotenv

from .athlete_profile import AthleteProfile, format_athlete_context
from .models import AnalysisResult, Race, WeeklyStats
from .race_manager import format_race_context

load_dotenv()

SYSTEM_PROMPT = """あなたはUphill Athleteの方法論に精通したランニングコーチです。
以下の原則に厳密に基づいてアドバイスを提供してください。

---

## Uphill Athlete 3大トレーニング原則

### 1. 継続性（Continuity）
トレーニングを継続することが最も重要です。怪我や過疲労は長期的損失を招きます。
- 1〜2日の休養は問題ないが、月間で訓練負荷の5%以上を不必要に減らさない
- 疲労サインがある場合は躊躇なく負荷を下げる

### 2. 段階性（Gradualness）
頻繁な穏やかな増加を重視し、散発的な高強度努力を避けます。
- **初心者**（週走行距離<50km）：年間最大25%増まで許容
- **中級者**（週50〜80km）：年間最大15%増まで
- **上級者**（週80km以上）：年間最大10%以下（オーバートレーニング予防）
- 1週間の増加は前週比10%以内が目安

### 3. 変調（Modulation）
3週間の負荷構築 + 1週間の回復（最も辛い週の**50%**の負荷）を繰り返します。
- 回復週を省略すると慢性疲労・怪我のリスクが急増する
- 回復週にはZ1中心の短いランのみ行う

---

## 4ゾーンシステム（Uphill Athlete）

| ゾーン | 心拍範囲 | 目的 | 推奨時間 |
|--------|---------|------|---------|
| Zone 1 | AeT×80〜90% | 回復・有酸素条件付け・脂肪代謝 | 30分〜数時間 |
| Zone 2 | AeT×90〜100% | 有酸素ベース構築・経済性向上 | 90分〜数時間 |
| Zone 3 | AeT〜AnT | 乳酸閾値・有酸素&無酸素容量 | 10〜60分 |
| Zone 4 | AnT〜最大 | 最大有酸素パワー・速筋線維 | 30秒〜8分（インターバル）|

**85/15ルール**: Z0+Z1+Z2で全トレーニング時間の85〜90%以上を占めることが目標（UAの正確な推奨値）。
- フェーズ別: Base 90%以上、Build 85%以上、Peak 80%以上
- トレイルランでは登りでのZ3スパイクは自然。平地ジョグでZ3に入る場合のみペース過多と判断する

---

## ADS（有酸素不全症候群）診断：10%テスト

AeT/AnT差（%）= (AnT心拍 - AeT心拍) / AnT心拍 × 100

- **差 > 10%**: ADS疑い → Z3・Z4は禁止。有酸素ベースを徹底強化してAeTを上げることが最優先
- **差 ≤ 10%**: 有酸素ベースが十分 → 高強度（Z3/Z4）を週間有酸素ボリュームの5〜10%まで導入可能

ADSがある場合は「高強度を頑張ればタイムが伸びる」という誤解を解き、Z1/Z2専念を強く指示してください。

---

## 心拍ドリフト（Cardiac Drift）の解釈

心拍ドリフト = 後半平均心拍 / 前半平均心拍 × 100 - 100

- **ドリフト < 3%**: 優秀。その強度の有酸素ベースが十分
- **ドリフト 3〜5%**: 許容範囲。ただし経過観察
- **ドリフト > 5%**: 要注意。その強度での有酸素ベースが不足。ペースを落とすか走行距離を短縮すべき
- **ドリフト > 10%**: 深刻。強度がAeT以上の可能性が高い

心拍ドリフトが高い場合は、AeT測定（心拍ドリフトテスト）を推奨してください。

---

## AeT測定ガイド（心拍ドリフトテスト）

1. 平坦路または一定勾配で60〜90分走（ペースを一定に保つ）
2. 前半30分と後半30分の平均心拍を比較
3. 後半が前半より **5%以上上昇** → その強度はAeT以上（ペース落とす）
4. 後半の上昇が **5%以内** → その心拍がAeT付近
5. ゆっくり始めてAeT付近の強度を見つける

---

## 30/30インターバル（Uphill Athlete推奨のZ4形式）

ADSがない場合のZ4インターバルは30/30形式を推奨：
- 30秒 Zone 4（最大心拍の92〜95%） + 30秒 Zone 1（完全回復）を繰り返す
- 1セット = 8〜10回の30/30（約8分）。最初は1セットから開始
- セット間：最低5分の完全回復
- ウォームアップ15〜20分、クールダウン15分を必ず含める
- 週1回まで。ADSがある場合は絶対に実施しない

---

## 筋持久力（Muscular Endurance: ME）トレーニング

- **対象フェーズ**: Build期・Peak期のみ（Base期では行わない）
- **内容**: 急勾配の登坂（17〜45度）でパワーハイキングまたはショートヒルリピート
- **目的**: 心拍系ではなく筋肉系の有酸素的疲労耐性を構築する
- **頻度**: 週1〜2回。疲労感を十分に回復してから次のセッションへ

---

## 訓練フェーズ別の詳細指針

### Base期（次のAレース12週以上前）
- **Z0+Z1+Z2: 90%以上**（Z3は原則禁止、ADSなし・AeT/AnT差≤10%でも控える）
- 週2回の一般的筋力トレーニング（スクワット、ランジ、コアワーク）
- ロングランは必ずZ2以下。心拍が上がりすぎたら即座にZ1まで落とす
- 有酸素ベース構築が最優先。焦りは禁物

### Build期（8〜12週前）
- **Z1+Z2: 90%以上**
- ME（筋持久力）セッション週1回を導入（ヒルリピートなど）
- ADS診断をクリアしている場合のみZ3セッション週1回まで追加可
- ボリュームを徐々に増加（前週比10%以内）

### Peak期（4〜8週前）
- **Z1+Z2: 80〜85%**（Z3/Z4: 15〜20%）
- MEセッション週1〜2回
- 30/30インターバル週1回（ADSなしの場合のみ）
- 最大ボリューム期。疲労管理を慎重に

### Taper期（4週以内）
- ボリュームを最困難週比で**40〜60%削減**
- 強度の高いセッションは短縮するが廃止しない（シャープネス維持）
- レース1週間前は完全にZ1+Z2のみ
- 「テーパータントラム」（不安感）は正常反応。焦って走りすぎないこと

### Recovery期（Aレース直後2週間）
- **Z1主体**。疲労感が完全に消えるまでZ2以上は禁止
- 最初の1週間は週3回・30分以内のショートランのみ
- 2週目から少しずつ距離を伸ばしてもよい

---

分析データに基づいて、具体的かつ実践的な日本語でアドバイスを提供してください。
数値根拠を示しながら、コーチとして明確な指示を出してください。"""


def _format_analysis_for_prompt(result: AnalysisResult, races: list[Race] | None = None, athlete_profile: AthleteProfile | None = None) -> str:
    """Format analysis result into a structured prompt."""
    dist = result.overall_zone_distribution
    zones = result.zones

    # ADS診断（10%テスト）
    aet_ant_gap_pct = (zones.ant_hr - zones.aet_hr) / zones.ant_hr * 100
    ads_status = (
        f"⚠️ ADS疑い（差{aet_ant_gap_pct:.1f}% > 10% → Z3/Z4禁止、有酸素ベース専念）"
        if aet_ant_gap_pct > 10
        else f"✅ 正常（差{aet_ant_gap_pct:.1f}% ≤ 10% → 高強度5〜10%まで導入可）"
    )

    zone_section = f"""## トレーニングデータ（過去{len(result.weeks)}週間）

### 全体概要
- 合計アクティビティ数: {result.total_activities}回
- 平均週間走行距離: {result.avg_weekly_km:.1f} km
- 平均週間トレーニング時間: {result.avg_weekly_h:.1f} 時間

### ゾーン設定 & ADS診断
- 有酸素閾値（AeT）心拍数: {zones.aet_hr} bpm
- 無酸素閾値（AnT）心拍数: {zones.ant_hr} bpm
- AeT/AnT差: {aet_ant_gap_pct:.1f}% → {ads_status}
- Zone 1: {zones.zone1_min:.0f}–{zones.zone1_max:.0f} bpm
- Zone 2: {zones.zone2_min:.0f}–{zones.zone2_max:.0f} bpm
- Zone 3: {zones.zone3_min:.0f}–{zones.zone3_max:.0f} bpm
- Zone 4: {zones.zone4_min:.0f}+ bpm

### ゾーン強度分布（過去{len(result.weeks)}週間の累計）
"""

    if dist.total_s > 0:
        zone_section += f"""- Zone 0 (超低強度/Z0): {dist.zone_pct(0):.1f}% ({dist.zone0_s/3600:.1f}h)
- Zone 1 (回復・脂肪代謝): {dist.zone_pct(1):.1f}% ({dist.zone1_s/3600:.1f}h)
- Zone 2 (有酸素ベース): {dist.zone_pct(2):.1f}% ({dist.zone2_s/3600:.1f}h)
- Zone 3 (乳酸閾値): {dist.zone_pct(3):.1f}% ({dist.zone3_s/3600:.1f}h)
- Zone 4 (最大有酸素): {dist.zone_pct(4):.1f}% ({dist.zone4_s/3600:.1f}h)
- **低強度(Z0+Z1+Z2)合計: {dist.low_intensity_pct:.1f}%** (目標: 85%以上)
- 高強度(Z3+Z4)合計: {dist.high_intensity_pct:.1f}%
"""
    else:
        zone_section += "- 心拍データがないため、ゾーン分布を計算できませんでした。\n"

    # Weekly volume trend
    vol_lines = []
    for ws in result.weeks[-8:]:  # last 8 weeks
        low_pct = ws.zone_distribution.low_intensity_pct if ws.zone_distribution.total_s > 0 else None
        low_info = f" Z1+Z2: {low_pct:.0f}%" if low_pct is not None else ""
        vol_lines.append(
            f"  Week {ws.week_start.strftime('%m/%d')}: "
            f"{ws.total_distance_km:.1f}km / {ws.total_time_h:.1f}h "
            f"({ws.activity_count}回){low_info}"
        )
    zone_section += "\n### 週次走行距離トレンド（最近8週）\n" + "\n".join(vol_lines)

    # Recovery week pattern
    zone_section += "\n\n### 周期化パターン\n"
    zone_section += (
        "- 回復週パターン検出: あり（3週増加+1週回復のサイクルを実践中）\n"
        if result.is_recovery_week_pattern
        else "- 回復週パターン検出: なし（計画的な回復週の導入を検討してください）\n"
    )

    # Recent activities with drift and zone info
    zone_section += "\n### 最近のアクティビティ（5件）\n"
    for act in reversed(result.recent_activities):
        hr_info = f" | 平均心拍: {act.average_heartrate:.0f}bpm" if act.average_heartrate else ""

        drift_info = ""
        if act.hr_drift_pct is not None:
            drift_info = f" | 心拍ドリフト: {act.hr_drift_pct:+.1f}%"
            if act.hr_drift_pct > 10:
                drift_info += "（深刻→強度過多）"
            elif act.hr_drift_pct > 5:
                drift_info += "（要注意→有酸素ベース不足の可能性）"
            elif act.hr_drift_pct > 3:
                drift_info += "（経過観察）"

        zone_dist_info = ""
        if act.zone_distribution and act.zone_distribution.total_s > 0:
            zd = act.zone_distribution
            zone_dist_info = (
                f" | このランのゾーン分布: Z1:{zd.zone_pct(1):.0f}%"
                f" Z2:{zd.zone_pct(2):.0f}%"
                f" Z3:{zd.zone_pct(3):.0f}%"
                f" Z4:{zd.zone_pct(4):.0f}%"
            )

        zone_section += (
            f"- {act.start_date.strftime('%m/%d')} {act.name}: "
            f"{act.distance_km:.1f}km, {act.moving_time_min:.0f}分"
            f"{hr_info}{drift_info}{zone_dist_info}\n"
        )

    # Race context
    if races is not None:
        zone_section += "\n" + format_race_context(races)

    # アスリートプロファイル
    if athlete_profile is not None:
        zone_section += "\n" + format_athlete_context(athlete_profile)

    return zone_section


def generate_advice(result: AnalysisResult, races: list[Race] | None = None, athlete_profile: AthleteProfile | None = None) -> str:
    """Generate training advice using Claude API based on analysis result."""
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    analysis_text = _format_analysis_for_prompt(result, races, athlete_profile)

    user_message = f"""{analysis_text}

## アドバイスの依頼

上記のデータに基づいて、以下の観点から具体的なトレーニングアドバイスを日本語で提供してください：

1. **現状の評価**: 80/20ルールへの適合度、ゾーン分布の問題点
2. **今週のおすすめトレーニング**: 具体的な練習内容（距離・時間・ゾーン）
3. **レースに向けた戦略**: 次のAレースまでの期間・フェーズを考慮した計画
4. **改善ポイント**: 特に注力すべき事項

Uphill Athleteの原則に従い、現在のトレーニングフェーズとレース目標を意識した実践的なアドバイスをお願いします。"""

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )

    return message.content[0].text  # type: ignore[union-attr]


def generate_weekly_summary_advice(
    result: AnalysisResult,
    current_week: WeeklyStats,
    races: list[Race] | None = None,
    training_phase: str = "Base",
) -> str:
    """Generate weekly summary advice with next week's goal (for Discord weekly summary)."""
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    zones = result.zones
    aet_ant_gap_pct = (zones.ant_hr - zones.aet_hr) / zones.ant_hr * 100
    ads_status = (
        f"⚠️ ADS疑い（差{aet_ant_gap_pct:.1f}% > 10% → Z3/Z4禁止）"
        if aet_ant_gap_pct > 10
        else f"✅ 正常（差{aet_ant_gap_pct:.1f}% ≤ 10%）"
    )

    # 今週の実績
    this_week_dist = current_week.total_distance_km
    this_week_h = current_week.total_time_h
    this_week_count = current_week.activity_count
    zd = current_week.zone_distribution
    low_pct = zd.low_intensity_pct if zd.total_s > 0 else None
    low_pct_str = f"{low_pct:.1f}%" if low_pct is not None else "データなし"

    # 直近8週のトレンド
    trend_lines = []
    for ws in result.weeks[-8:]:
        wlow = ws.zone_distribution.low_intensity_pct if ws.zone_distribution.total_s > 0 else None
        wlow_str = f" Z1+Z2:{wlow:.0f}%" if wlow is not None else ""
        trend_lines.append(
            f"  Week {ws.week_start.strftime('%m/%d')}: "
            f"{ws.total_distance_km:.1f}km / {ws.total_time_h:.1f}h "
            f"({ws.activity_count}回){wlow_str}"
        )
    trend_text = "\n".join(trend_lines)

    race_context = format_race_context(races) if races else "レース予定なし"

    user_message = f"""## 今週（{current_week.week_start.strftime('%m/%d')}週）のトレーニング実績

### 今週の実績
- 走行距離: {this_week_dist:.1f} km
- トレーニング時間: {this_week_h:.1f} 時間
- アクティビティ数: {this_week_count} 回
- 低強度(Z1+Z2)割合: {low_pct_str}（目標: 80%以上）
- ゾーン分布: Z1:{zd.zone_pct(1):.1f}% / Z2:{zd.zone_pct(2):.1f}% / Z3:{zd.zone_pct(3):.1f}% / Z4:{zd.zone_pct(4):.1f}%

### ADS診断 & ゾーン設定
- AeT: {zones.aet_hr} bpm / AnT: {zones.ant_hr} bpm
- ADS診断: {ads_status}

### 周期化パターン
- 回復週パターン: {'あり（3:1サイクル実践中）' if result.is_recovery_week_pattern else 'なし（回復週の導入を検討）'}

### 直近8週のトレンド
{trend_text}

### 平均週間実績
- 平均走行距離: {result.avg_weekly_km:.1f} km/週
- 平均時間: {result.avg_weekly_h:.1f} h/週

{race_context}

## 依頼

現在のトレーニングフェーズ: **{training_phase}**

以下の構成で週次サマリーを日本語で提供してください：

**1. 今週の評価（2〜3文）**
80/20ルールの達成度、3:1サイクルの状況、ADS診断結果を踏まえた評価。

**2. 来週の目標**
- 推奨走行距離: ○○ km（理由を1文で）
- 推奨トレーニング時間: ○○ 時間
- 重点ゾーン: Zone ○（理由）

**3. 来週の具体的スケジュール案（月〜日）**
各日について「休養」「Z1 ○km・○分」「Z2 ○km・○分」「MEセッション ○分」など具体的に記載。
現在のフェーズ・ADSステータス・レース日程を考慮すること。

**4. 注意事項（1〜2文）**
特に気をつけるべきポイント。"""

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1500,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )

    return message.content[0].text  # type: ignore[union-attr]


def generate_single_activity_advice(
    activity_summary: str, result: AnalysisResult, races: list[Race] | None = None,
    athlete_profile: AthleteProfile | None = None,
) -> str:
    """Generate a short advice for a single new activity (for Discord notification)."""
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    race_context = format_race_context(races) if races else ""

    zones = result.zones
    aet_ant_gap_pct = (zones.ant_hr - zones.aet_hr) / zones.ant_hr * 100
    ads_note = "（ADS疑い→Z3/Z4禁止）" if aet_ant_gap_pct > 10 else "（高強度5〜10%まで可）"

    user_message = f"""## 新しいランニングアクティビティ
{activity_summary}

## 直近のトレーニングコンテキスト（過去12週）
- 平均週間走行距離: {result.avg_weekly_km:.1f} km
- 低強度(Z0+Z1+Z2)割合: {result.overall_zone_distribution.low_intensity_pct:.1f}%（目標85%以上）
- 回復週パターン: {'あり' if result.is_recovery_week_pattern else 'なし'}
- AeT: {zones.aet_hr} bpm / AnT: {zones.ant_hr} bpm / AeT-AnT差: {aet_ant_gap_pct:.1f}%{ads_note}

{race_context}

## 依頼
この1回のランについて、3〜5文で簡潔なフィードバックを日本語で提供してください。
- 心拍ドリフト・ゾーン分布への評価
- ADS診断の状況を踏まえたゾーンコントロールへのコメント
- 次回へのアドバイス
レース目標も意識してください。"""

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=800,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )

    return message.content[0].text  # type: ignore[union-attr]
