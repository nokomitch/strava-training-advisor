"""AI training advice generation using Claude API."""

import os

import anthropic
from dotenv import load_dotenv

from .models import AnalysisResult, Race
from .race_manager import format_race_context

load_dotenv()

SYSTEM_PROMPT = """あなたはUphill Athleteの方法論に精通したランニングコーチです。
以下の原則に基づいてアドバイスを提供してください：

1. **継続性と漸進性**: トレーニングは段階的に進め、週間走行距離の増加は10%以内に抑える
2. **モジュレーション**: 3週間の負荷増加 + 1週間の回復（ピーク週の50%程度）のサイクルを推奨する
3. **低強度重視（80/20ルール）**: トレーニング時間の80%以上をゾーン1-2（有酸素閾値以下）で行う
4. **4ゾーンシステム**:
   - Zone 1: AeT×80%〜90%（非常に楽、会話可能）
   - Zone 2: AeT×90%〜AeT（楽〜中程度、有酸素ベース構築の主要ゾーン）
   - Zone 3: AeT〜AnT（中〜ハード、乳酸閾値トレーニング）
   - Zone 4: AnT〜最大心拍（非常にハード、無酸素トレーニング）
5. **レース準備の周期化**: レース優先度と残り期間に応じてフェーズを調整する
   - Base期（12週以上前）: 有酸素ベース中心、Z1-Z2 90%以上
   - Build期（8-12週前）: ボリューム増加、週1回のZ3セッション追加可
   - Peak期（4-8週前）: 最大負荷、Z3-Z4セッション増加
   - Taper期（4週前以内）: ボリューム削減、強度維持
   - Recovery期（Aレース直後2週）: 完全回復優先

分析データに基づいて、具体的かつ実践的な日本語でアドバイスを提供してください。"""


def _format_analysis_for_prompt(result: AnalysisResult, races: list[Race] | None = None) -> str:
    """Format analysis result into a structured prompt."""
    dist = result.overall_zone_distribution
    zones = result.zones

    zone_section = f"""## トレーニングデータ（過去{len(result.weeks)}週間）

### 全体概要
- 合計アクティビティ数: {result.total_activities}回
- 平均週間走行距離: {result.avg_weekly_km:.1f} km
- 平均週間トレーニング時間: {result.avg_weekly_h:.1f} 時間

### ゾーン設定
- 有酸素閾値（AeT）心拍数: {zones.aet_hr} bpm
- 無酸素閾値（AnT）心拍数: {zones.ant_hr} bpm
- Zone 1: {zones.zone1_min:.0f}–{zones.zone1_max:.0f} bpm
- Zone 2: {zones.zone2_min:.0f}–{zones.zone2_max:.0f} bpm
- Zone 3: {zones.zone3_min:.0f}–{zones.zone3_max:.0f} bpm
- Zone 4: {zones.zone4_min:.0f}+ bpm

### ゾーン強度分布（心拍データあり）
"""

    if dist.total_s > 0:
        zone_section += f"""- Zone 1 (非常に楽): {dist.zone_pct(1):.1f}% ({dist.zone1_s/3600:.1f}h)
- Zone 2 (楽〜中程度): {dist.zone_pct(2):.1f}% ({dist.zone2_s/3600:.1f}h)
- Zone 3 (中〜ハード): {dist.zone_pct(3):.1f}% ({dist.zone3_s/3600:.1f}h)
- Zone 4 (非常にハード): {dist.zone_pct(4):.1f}% ({dist.zone4_s/3600:.1f}h)
- **低強度(Z1+Z2)合計: {dist.low_intensity_pct:.1f}%** (目標: 80%以上)
- 高強度(Z3+Z4)合計: {dist.high_intensity_pct:.1f}%
"""
    else:
        zone_section += "- 心拍データがないため、ゾーン分布を計算できませんでした。\n"

    # Weekly volume trend
    vol_lines = []
    for ws in result.weeks[-8:]:  # last 8 weeks
        vol_lines.append(
            f"  Week {ws.week_start.strftime('%m/%d')}: "
            f"{ws.total_distance_km:.1f}km / {ws.total_time_h:.1f}h "
            f"({ws.activity_count}回)"
        )
    zone_section += "\n### 週次走行距離トレンド（最近8週）\n" + "\n".join(vol_lines)

    # Recovery week pattern
    zone_section += "\n\n### 周期化パターン\n"
    zone_section += (
        "- 回復週パターン検出: あり（3週増加+1週回復のサイクルを実践中）\n"
        if result.is_recovery_week_pattern
        else "- 回復週パターン検出: なし（計画的な回復週の導入を検討してください）\n"
    )

    # Recent activities
    zone_section += "\n### 最近のアクティビティ（5件）\n"
    for act in reversed(result.recent_activities):
        hr_info = f" | 平均心拍: {act.average_heartrate:.0f}bpm" if act.average_heartrate else ""
        zone_section += (
            f"- {act.start_date.strftime('%m/%d')} {act.name}: "
            f"{act.distance_km:.1f}km, {act.moving_time_min:.0f}分{hr_info}\n"
        )

    # Race context
    if races is not None:
        zone_section += "\n" + format_race_context(races)

    return zone_section


def generate_advice(result: AnalysisResult, races: list[Race] | None = None) -> str:
    """Generate training advice using Claude API based on analysis result."""
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    analysis_text = _format_analysis_for_prompt(result, races)

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


def generate_single_activity_advice(
    activity_summary: str, result: AnalysisResult, races: list[Race] | None = None
) -> str:
    """Generate a short advice for a single new activity (for Discord notification)."""
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    race_context = format_race_context(races) if races else ""

    user_message = f"""## 新しいランニングアクティビティ
{activity_summary}

## 直近のトレーニングコンテキスト（過去12週）
- 平均週間走行距離: {result.avg_weekly_km:.1f} km
- 低強度(Z1+Z2)割合: {result.overall_zone_distribution.low_intensity_pct:.1f}%
- 回復週パターン: {'あり' if result.is_recovery_week_pattern else 'なし'}

{race_context}

## 依頼
この1回のランについて、3〜5文で簡潔なフィードバックを日本語で提供してください。
ゾーン分布の評価、今後への一言アドバイスを含めてください。レース目標も意識してください。"""

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=400,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )

    return message.content[0].text  # type: ignore[union-attr]
