"""Strava API client with OAuth2 authentication and activity fetching."""

import os
import time
from datetime import datetime, timedelta, timezone

import requests
from dotenv import load_dotenv, set_key

from .models import Activity

load_dotenv()

STRAVA_API_BASE = "https://www.strava.com/api/v3"
STRAVA_AUTH_URL = "https://www.strava.com/oauth/authorize"
STRAVA_TOKEN_URL = "https://www.strava.com/oauth/token"


class StravaClient:
    """Strava API client with automatic token refresh."""

    def __init__(self) -> None:
        self.client_id = os.getenv("STRAVA_CLIENT_ID", "")
        self.client_secret = os.getenv("STRAVA_CLIENT_SECRET", "")
        self.access_token = os.getenv("STRAVA_ACCESS_TOKEN", "")
        self.refresh_token = os.getenv("STRAVA_REFRESH_TOKEN", "")
        self.token_expires_at = int(os.getenv("STRAVA_TOKEN_EXPIRES_AT", "0"))
        self._env_path = self._find_env_path()

        if not self.client_id or not self.client_secret:
            raise ValueError(
                "STRAVA_CLIENT_ID and STRAVA_CLIENT_SECRET must be set in .env"
            )

    def _find_env_path(self) -> str:
        """Find the .env file path."""
        script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        return os.path.join(script_dir, ".env")

    def _ensure_valid_token(self) -> None:
        """Refresh access token if expired."""
        if not self.access_token:
            raise ValueError(
                "No access token found. Run 'uv run python scripts/setup_oauth.py' first."
            )

        now = int(time.time())
        if now >= self.token_expires_at - 300:  # refresh 5 minutes early
            self._refresh_token()

    def _refresh_token(self) -> None:
        """Exchange refresh token for a new access token."""
        response = requests.post(
            STRAVA_TOKEN_URL,
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "grant_type": "refresh_token",
                "refresh_token": self.refresh_token,
            },
            timeout=30,
        )
        response.raise_for_status()
        token_data = response.json()

        self.access_token = token_data["access_token"]
        self.refresh_token = token_data["refresh_token"]
        self.token_expires_at = token_data["expires_at"]

        # Persist new tokens to .env
        set_key(self._env_path, "STRAVA_ACCESS_TOKEN", self.access_token)
        set_key(self._env_path, "STRAVA_REFRESH_TOKEN", self.refresh_token)
        set_key(self._env_path, "STRAVA_TOKEN_EXPIRES_AT", str(self.token_expires_at))

    def _get(self, path: str, params: dict | None = None) -> dict | list:
        """Make an authenticated GET request."""
        self._ensure_valid_token()
        response = requests.get(
            f"{STRAVA_API_BASE}{path}",
            headers={"Authorization": f"Bearer {self.access_token}"},
            params=params or {},
            timeout=30,
        )
        response.raise_for_status()
        return response.json()

    def get_athlete(self) -> dict:
        """Fetch the authenticated athlete's profile."""
        return self._get("/athlete")  # type: ignore[return-value]

    def fetch_activities(self, weeks: int = 12) -> list[Activity]:
        """Fetch running activities for the past N weeks with HR streams."""
        since = datetime.now(timezone.utc) - timedelta(weeks=weeks)
        after_ts = int(since.timestamp())

        # Paginate through all activities
        all_raw = []
        page = 1
        while True:
            batch = self._get(
                "/athlete/activities",
                {"after": after_ts, "per_page": 100, "page": page},
            )
            if not batch:
                break
            all_raw.extend(batch)  # type: ignore[arg-type]
            if len(batch) < 100:  # type: ignore[arg-type]
                break
            page += 1

        # Filter to running activities only
        running = [
            r for r in all_raw
            if r.get("sport_type") in ("Run", "TrailRun", "VirtualRun")
        ]

        activities = []
        for raw in running:
            activity = self._parse_activity(raw)
            # Fetch detailed streams for activities with HR data
            if raw.get("has_heartrate"):
                try:
                    activity = self._enrich_with_streams(activity)
                except Exception:
                    pass  # streams unavailable; use summary HR only
            activities.append(activity)

        return sorted(activities, key=lambda a: a.start_date)

    def _parse_activity(self, raw: dict) -> Activity:
        """Parse a raw Strava activity dict into an Activity model."""
        return Activity(
            id=raw["id"],
            name=raw.get("name", ""),
            sport_type=raw.get("sport_type", "Run"),
            start_date=datetime.fromisoformat(
                raw["start_date"].replace("Z", "+00:00")
            ),
            distance_m=float(raw.get("distance", 0)),
            moving_time_s=int(raw.get("moving_time", 0)),
            elapsed_time_s=int(raw.get("elapsed_time", 0)),
            total_elevation_gain_m=float(raw.get("total_elevation_gain", 0)),
            average_heartrate=raw.get("average_heartrate"),
            max_heartrate=raw.get("max_heartrate"),
            average_speed_mps=float(raw.get("average_speed", 0)),
        )

    def _enrich_with_streams(self, activity: Activity) -> Activity:
        """Fetch heartrate and time streams and attach them to the activity."""
        streams = self._get(
            f"/activities/{activity.id}/streams",
            {"keys": "heartrate,time", "key_by_type": "true"},
        )
        if isinstance(streams, dict):
            if "heartrate" in streams:
                activity.heartrate_stream = streams["heartrate"]["data"]
            if "time" in streams:
                activity.time_stream = streams["time"]["data"]
        return activity
