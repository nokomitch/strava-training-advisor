"""Uphill Athlete-based training analysis."""

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from .models import Activity, AnalysisResult, TrainingZones, WeeklyStats, ZoneDistribution

_JST = ZoneInfo("Asia/Tokyo")


def _compute_zone_distribution(
    activities: list[Activity], zones: TrainingZones
) -> ZoneDistribution:
    """Compute total time in each zone across a list of activities."""
    dist = ZoneDistribution()

    for activity in activities:
        if activity.heartrate_stream and activity.time_stream:
            # Use second-by-second stream data
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
            # Fallback: classify average HR for entire activity duration
            zone = zones.classify_hr(activity.average_heartrate)
            duration_s = activity.moving_time_s
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

    return dist


def _group_by_week(activities: list[Activity]) -> dict[datetime, list[Activity]]:
    """Group activities by ISO week start (Monday)."""
    weeks: dict[datetime, list[Activity]] = defaultdict(list)
    for activity in activities:
        # Convert to JST-naive for grouping (週の区切りを日本時間基準にする)
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


def analyze(activities: list[Activity], zones: TrainingZones) -> AnalysisResult:
    """
    Analyze activities using Uphill Athlete principles.

    Args:
        activities: Chronologically sorted list of running activities.
        zones: TrainingZones with AeT and AnT thresholds.

    Returns:
        AnalysisResult with zone distribution, weekly stats, and trend data.
    """
    weeks_map = _group_by_week(activities)
    weekly_stats: list[WeeklyStats] = []

    for week_start, week_acts in weeks_map.items():
        zone_dist = _compute_zone_distribution(week_acts, zones)
        weekly_stats.append(
            WeeklyStats(
                week_start=week_start,
                activities=week_acts,
                zone_distribution=zone_dist,
            )
        )

    # アクティビティ単位のゾーン分布を計算（心拍ストリームがある場合のみ）
    for activity in activities:
        if activity.heartrate_stream:
            activity.zone_distribution = _compute_zone_distribution([activity], zones)

    overall_dist = _compute_zone_distribution(activities, zones)
    weekly_volumes = [ws.total_distance_km for ws in weekly_stats]
    recovery_pattern = _check_recovery_week_pattern(weekly_volumes)

    avg_weekly_km = sum(weekly_volumes) / len(weekly_volumes) if weekly_volumes else 0.0
    avg_weekly_h = (
        sum(ws.total_time_h for ws in weekly_stats) / len(weekly_stats)
        if weekly_stats
        else 0.0
    )

    # Recent 5 activities for display
    recent = activities[-5:] if len(activities) >= 5 else activities

    return AnalysisResult(
        weeks=weekly_stats,
        overall_zone_distribution=overall_dist,
        zones=zones,
        recent_activities=recent,
        weekly_volume_trend=weekly_volumes,
        is_recovery_week_pattern=recovery_pattern,
        avg_weekly_km=avg_weekly_km,
        avg_weekly_h=avg_weekly_h,
        total_activities=len(activities),
    )
