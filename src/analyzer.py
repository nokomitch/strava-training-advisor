"""Uphill Athlete-based training analysis."""

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from math import erf, sqrt
from zoneinfo import ZoneInfo

from .models import (
    Activity, ActivityAnalysis, AnalysisResult, TrainingZones,
    WeeklyStats, ZoneDistribution,
)

_JST = ZoneInfo("Asia/Tokyo")


def _estimate_zone_distribution_from_avg_hr(
    avg_hr: float,
    max_hr: float | None,
    duration_s: int,
    zones: TrainingZones,
) -> ZoneDistribution:
    """平均HRから正規分布を仮定してゾーン分布を推定する。
    ストリームデータがない場合のフォールバック。全時間を1ゾーンに割り当てる旧ロジックより精度が高い。
    """
    if max_hr and max_hr > avg_hr:
        sigma = (max_hr - avg_hr) / 2.0
        sigma = max(sigma, 5.0)
    else:
        sigma = 10.0

    def normal_cdf(x: float) -> float:
        return 0.5 * (1.0 + erf((x - avg_hr) / (sigma * sqrt(2.0))))

    p_below_z1 = normal_cdf(zones.zone1_min)
    p_below_z2 = normal_cdf(zones.zone1_max)
    p_below_z3 = normal_cdf(zones.zone2_max)
    p_below_z4 = normal_cdf(zones.zone3_max)

    return ZoneDistribution(
        zone0_s=p_below_z1 * duration_s,
        zone1_s=(p_below_z2 - p_below_z1) * duration_s,
        zone2_s=(p_below_z3 - p_below_z2) * duration_s,
        zone3_s=(p_below_z4 - p_below_z3) * duration_s,
        zone4_s=(1.0 - p_below_z4) * duration_s,
    )


def _compute_zone_distribution(
    activities: list[Activity], zones: TrainingZones
) -> ZoneDistribution:
    """Compute total time in each zone across a list of activities."""
    dist = ZoneDistribution()

    for activity in activities:
        if not activity.is_running:
            continue
        if activity.heartrate_stream and activity.time_stream:
            for i, hr in enumerate(activity.heartrate_stream):
                if i + 1 < len(activity.time_stream):
                    duration_s = activity.time_stream[i + 1] - activity.time_stream[i]
                else:
                    duration_s = 1

                zone = zones.classify_hr(hr)
                if zone == 0:
                    dist.zone0_s += duration_s
                elif zone == 1:
                    dist.zone1_s += duration_s
                elif zone == 2:
                    dist.zone2_s += duration_s
                elif zone == 3:
                    dist.zone3_s += duration_s
                elif zone == 4:
                    dist.zone4_s += duration_s

        elif activity.average_heartrate:
            estimated = _estimate_zone_distribution_from_avg_hr(
                avg_hr=activity.average_heartrate,
                max_hr=activity.max_heartrate,
                duration_s=activity.moving_time_s,
                zones=zones,
            )
            dist.zone0_s += estimated.zone0_s
            dist.zone1_s += estimated.zone1_s
            dist.zone2_s += estimated.zone2_s
            dist.zone3_s += estimated.zone3_s
            dist.zone4_s += estimated.zone4_s

    return dist


def compute_single_activity_zones(activity: Activity, zones: TrainingZones) -> ZoneDistribution:
    """1つのアクティビティのゾーン分布を計算する。"""
    return _compute_zone_distribution([activity], zones)


def classify_activity_type(zone_dist: ZoneDistribution, duration_s: int) -> str:
    """ゾーン分布と時間からアクティビティタイプを分類する。"""
    if zone_dist.total_s == 0:
        return "unknown"

    low_pct = zone_dist.low_intensity_pct  # Z0+Z1+Z2
    z3_pct = zone_dist.zone_pct(3)
    z4_pct = zone_dist.zone_pct(4)
    duration_min = duration_s / 60

    if low_pct >= 90 and duration_min < 45:
        return "recovery"
    elif z4_pct >= 10:
        return "speed"
    elif z3_pct >= 20:
        return "tempo"
    elif low_pct >= 80 and duration_min >= 90:
        return "long_run"
    elif low_pct >= 80:
        return "easy"
    else:
        return "mixed"


def _group_by_week(activities: list[Activity]) -> dict[datetime, list[Activity]]:
    """Group activities by ISO week start (Monday), using JST timezone."""
    weeks: dict[datetime, list[Activity]] = defaultdict(list)
    for activity in activities:
        # 週の区切りを日本時間基準にする
        d = activity.start_date.astimezone(_JST).replace(tzinfo=None)
        week_start = d - timedelta(days=d.weekday())
        week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)
        weeks[week_start].append(activity)
    return dict(sorted(weeks.items()))


def _check_recovery_week_pattern(weekly_volumes: list[float]) -> bool:
    """
    Check if training follows a 3-weeks-load + 1-week-recovery pattern.
    Returns True if at least one recovery week (volume drop >=30%) is detected
    within a 4-week window.
    """
    if len(weekly_volumes) < 4:
        return False

    for i in range(len(weekly_volumes) - 3):
        window = weekly_volumes[i : i + 4]
        peak = max(window[:3])
        if peak > 0 and window[3] <= peak * 0.70:
            return True
    return False


def compute_weekly_build_rates(weekly_volumes: list[float]) -> list[float | None]:
    """週次ビルド率（前週比%）を計算する。最初の週は None。"""
    rates: list[float | None] = [None]
    for i in range(1, len(weekly_volumes)):
        prev = weekly_volumes[i - 1]
        if prev > 0:
            rates.append((weekly_volumes[i] - prev) / prev * 100)
        else:
            rates.append(None)
    return rates


def analyze(
    activities: list[Activity],
    zones: TrainingZones,
    strength_activities: list[Activity] | None = None,
) -> AnalysisResult:
    """
    Analyze activities using Uphill Athlete principles.

    Args:
        activities: Chronologically sorted list of activities (running + strength mixed).
        zones: TrainingZones with AeT and AnT thresholds.
        strength_activities: Optional explicit list of strength activities.

    Returns:
        AnalysisResult with zone distribution, weekly stats, and trend data.
    """
    running = [a for a in activities if a.is_running]
    strength = strength_activities if strength_activities is not None else [a for a in activities if a.is_strength]

    weeks_map = _group_by_week(running)

    # 筋トレを週次グルーピング（JST基準）
    strength_by_week: dict[datetime, int] = defaultdict(int)
    for act in strength:
        d = act.start_date.astimezone(_JST).replace(tzinfo=None)
        week_start = d - timedelta(days=d.weekday())
        week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)
        strength_by_week[week_start] += 1

    weekly_stats: list[WeeklyStats] = []
    for week_start, week_acts in weeks_map.items():
        zone_dist = _compute_zone_distribution(week_acts, zones)
        weekly_stats.append(
            WeeklyStats(
                week_start=week_start,
                activities=week_acts,
                zone_distribution=zone_dist,
                strength_count=strength_by_week.get(week_start, 0),
            )
        )

    # アクティビティ単位のゾーン分布を設定（心拍ストリームがある場合のみ）
    for activity in running:
        if activity.heartrate_stream:
            activity.zone_distribution = _compute_zone_distribution([activity], zones)

    overall_dist = _compute_zone_distribution(running, zones)
    weekly_volumes = [ws.total_distance_km for ws in weekly_stats]
    recovery_pattern = _check_recovery_week_pattern(weekly_volumes)
    build_rates = compute_weekly_build_rates(weekly_volumes)

    avg_weekly_km = sum(weekly_volumes) / len(weekly_volumes) if weekly_volumes else 0.0
    avg_weekly_h = (
        sum(ws.total_time_h for ws in weekly_stats) / len(weekly_stats)
        if weekly_stats
        else 0.0
    )

    # 最近5件のランニングアクティビティの個別分析
    recent = running[-5:] if len(running) >= 5 else running
    activity_analyses = []
    for act in recent:
        zone_dist_single = compute_single_activity_zones(act, zones)
        act_type = classify_activity_type(zone_dist_single, act.moving_time_s)
        activity_analyses.append(ActivityAnalysis(
            activity=act,
            zone_distribution=zone_dist_single,
            activity_type=act_type,
        ))

    strength_counts = [ws.strength_count for ws in weekly_stats]

    return AnalysisResult(
        weeks=weekly_stats,
        overall_zone_distribution=overall_dist,
        zones=zones,
        recent_activities=recent,
        weekly_volume_trend=weekly_volumes,
        is_recovery_week_pattern=recovery_pattern,
        avg_weekly_km=avg_weekly_km,
        avg_weekly_h=avg_weekly_h,
        total_activities=len(running),
        strength_activities=strength,
        activity_analyses=activity_analyses,
        weekly_build_rates=build_rates,
        strength_counts_per_week=strength_counts,
    )
