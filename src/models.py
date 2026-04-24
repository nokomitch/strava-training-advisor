"""Data models for Strava Training Advisor."""

import statistics
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Literal, Optional
from zoneinfo import ZoneInfo


ActivityType = Literal["easy", "long_run", "tempo", "speed", "recovery", "mixed", "unknown"]


@dataclass
class Activity:
    """A single Strava activity."""

    id: int
    name: str
    sport_type: str
    start_date: datetime
    distance_m: float
    moving_time_s: int
    elapsed_time_s: int
    total_elevation_gain_m: float
    average_heartrate: Optional[float]
    max_heartrate: Optional[float]
    average_speed_mps: float
    heartrate_stream: list[int] = field(default_factory=list)
    time_stream: list[int] = field(default_factory=list)
    zone_distribution: Optional["ZoneDistribution"] = field(default=None)
    activity_type: str = "unknown"  # ActivityType

    RUNNING_TYPES = frozenset({"Run", "TrailRun", "VirtualRun"})
    STRENGTH_TYPES = frozenset({"WeightTraining", "Workout", "Crossfit", "Yoga"})

    @property
    def is_running(self) -> bool:
        return self.sport_type in self.RUNNING_TYPES

    @property
    def is_strength(self) -> bool:
        return self.sport_type in self.STRENGTH_TYPES

    def compute_hr_drift(self, warmup_s: int = 0) -> Optional[float]:
        """後半平均HR / 前半平均HR × 100 - 100（ドリフト%）。
        warmup_s: ウォームアップとして除外する先頭の秒数。time_stream を使って除外。
        正値 = 後半に心拍上昇（有酸素ベース弱さの指標）。ストリームがない場合は None。"""
        if not self.heartrate_stream or len(self.heartrate_stream) < 4:
            return None
        if warmup_s > 0 and self.time_stream:
            start_idx = next((i for i, t in enumerate(self.time_stream) if t >= warmup_s), None)
            if start_idx is None or len(self.heartrate_stream) - start_idx < 4:
                return None
            hr = self.heartrate_stream[start_idx:]
        else:
            hr = self.heartrate_stream
        mid = len(hr) // 2
        first_half_avg = sum(hr[:mid]) / mid
        second_half_avg = sum(hr[mid:]) / (len(hr) - mid)
        return (second_half_avg / first_half_avg - 1) * 100

    @property
    def hr_drift_pct(self) -> Optional[float]:
        """ウォームアップなしのドリフト%（後方互換用）。"""
        return self.compute_hr_drift(0)

    @property
    def hr_stability(self) -> Optional[float]:
        """心拍の標準偏差（bpm）。ペース一貫性の指標。ストリームがない場合は None。"""
        if not self.heartrate_stream or len(self.heartrate_stream) < 2:
            return None
        return statistics.stdev(self.heartrate_stream)

    @property
    def distance_km(self) -> float:
        return self.distance_m / 1000

    @property
    def moving_time_min(self) -> float:
        return self.moving_time_s / 60

    @property
    def moving_time_h(self) -> float:
        return self.moving_time_s / 3600

    @property
    def average_pace_min_per_km(self) -> float:
        if self.average_speed_mps > 0:
            return 1000 / (self.average_speed_mps * 60)
        return 0.0


@dataclass
class TrainingZones:
    """Uphill Athlete 4-zone system based on AeT and AnT."""

    aet_hr: int  # Aerobic Threshold heart rate
    ant_hr: int  # Anaerobic Threshold heart rate

    @property
    def zone1_min(self) -> float:
        return self.aet_hr * 0.80

    @property
    def zone1_max(self) -> float:
        return self.aet_hr * 0.90

    @property
    def zone2_min(self) -> float:
        return self.aet_hr * 0.90

    @property
    def zone2_max(self) -> float:
        return float(self.aet_hr)

    @property
    def zone3_min(self) -> float:
        return float(self.aet_hr)

    @property
    def zone3_max(self) -> float:
        return float(self.ant_hr)

    @property
    def zone4_min(self) -> float:
        return float(self.ant_hr)

    def classify_hr(self, hr: float) -> int:
        """Classify a heart rate value into zones 1-4 (0 = below Z1)."""
        if hr < self.zone1_min:
            return 0
        elif hr <= self.zone1_max:
            return 1
        elif hr <= self.zone2_max:
            return 2
        elif hr <= self.zone3_max:
            return 3
        else:
            return 4


@dataclass
class ZoneDistribution:
    """Time spent in each training zone (in seconds)."""

    zone0_s: float = 0  # Below Zone 1
    zone1_s: float = 0
    zone2_s: float = 0
    zone3_s: float = 0
    zone4_s: float = 0

    @property
    def total_s(self) -> float:
        # Z0（Z1未満）も含めた全時間を分母にすることで、
        # ウォームアップ・下り・歩きが多いトレイルランでも Z3 が過大表示されない
        return self.zone0_s + self.zone1_s + self.zone2_s + self.zone3_s + self.zone4_s

    @property
    def low_intensity_pct(self) -> float:
        """Percentage of time in Zone 0+1+2 (recovery + easy aerobic, target: >=85%)."""
        if self.total_s == 0:
            return 0.0
        return (self.zone0_s + self.zone1_s + self.zone2_s) / self.total_s * 100

    @property
    def high_intensity_pct(self) -> float:
        """Percentage of time in Zone 3+4."""
        if self.total_s == 0:
            return 0.0
        return (self.zone3_s + self.zone4_s) / self.total_s * 100

    def zone_pct(self, zone: int) -> float:
        if self.total_s == 0:
            return 0.0
        zone_map = {0: self.zone0_s, 1: self.zone1_s, 2: self.zone2_s, 3: self.zone3_s, 4: self.zone4_s}
        return zone_map.get(zone, 0) / self.total_s * 100


@dataclass
class ActivityAnalysis:
    """Per-activity zone breakdown and classification."""

    activity: Activity
    zone_distribution: ZoneDistribution
    activity_type: str  # ActivityType


@dataclass
class WeeklyStats:
    """Training statistics for a single week."""

    week_start: datetime
    activities: list[Activity] = field(default_factory=list)
    zone_distribution: ZoneDistribution = field(default_factory=ZoneDistribution)
    strength_count: int = 0

    @property
    def total_distance_km(self) -> float:
        return sum(a.distance_km for a in self.activities)

    @property
    def total_time_h(self) -> float:
        return sum(a.moving_time_h for a in self.activities)

    @property
    def activity_count(self) -> int:
        return len(self.activities)


RacePriority = Literal["A", "B", "C"]
TrainingPhase = Literal["Base", "Build", "Peak", "Taper", "Recovery"]


@dataclass
class Race:
    """An upcoming race event."""

    name: str
    date: date
    priority: RacePriority  # A=最重要, B=重要, C=参加程度
    distance_km: float
    notes: str = ""

    @property
    def days_until(self) -> int:
        today_jst = datetime.now(ZoneInfo("Asia/Tokyo")).date()
        return (self.date - today_jst).days

    @property
    def is_past(self) -> bool:
        return self.days_until < 0


@dataclass
class AnalysisResult:
    """Complete analysis result for training advice."""

    weeks: list[WeeklyStats]
    overall_zone_distribution: ZoneDistribution
    zones: TrainingZones
    recent_activities: list[Activity]
    weekly_volume_trend: list[float]  # km per week, chronological
    is_recovery_week_pattern: bool
    avg_weekly_km: float
    avg_weekly_h: float
    total_activities: int
    # Extensions for strength tracking and per-activity analysis
    strength_activities: list[Activity] = field(default_factory=list)
    activity_analyses: list["ActivityAnalysis"] = field(default_factory=list)
    weekly_build_rates: list[Optional[float]] = field(default_factory=list)
    strength_counts_per_week: list[int] = field(default_factory=list)
