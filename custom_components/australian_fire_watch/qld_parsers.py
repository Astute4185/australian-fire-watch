"""Pure Queensland ArcGIS response normalization; no Home Assistant dependencies."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

# Queensland uses AEST all year. A fixed offset avoids first-use ZoneInfo disk I/O
# on Home Assistant's event loop.
AEST = timezone(timedelta(hours=10), name="AEST")
UTC = timezone.utc
VALID_RATINGS = frozenset(
    {"No Rating", "Moderate", "High", "Extreme", "Catastrophic"}
)


class QldDataError(ValueError):
    """The upstream response is not trustworthy for a boolean/rating state."""


def _timestamp(value: Any) -> datetime | None:
    """Convert an ArcGIS epoch-millisecond field to aware UTC datetime."""
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise QldDataError("Invalid ArcGIS timestamp type")
    try:
        return datetime.fromtimestamp(value / 1000, UTC)
    except (OverflowError, OSError, ValueError) as exc:
        raise QldDataError("Invalid ArcGIS timestamp value") from exc


def _features(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict) or payload.get("error") is not None:
        raise QldDataError("ArcGIS returned an error")
    features = payload.get("features")
    if not isinstance(features, list):
        raise QldDataError("ArcGIS features array missing")
    result = []
    for item in features:
        if not isinstance(item, dict) or not isinstance(item.get("attributes"), dict):
            raise QldDataError("Invalid ArcGIS feature attributes")
        result.append(item["attributes"])
    return result


def _one_feature(payload: Any) -> dict[str, Any] | None:
    features = _features(payload)
    if len(features) > 1 or payload.get("exceededTransferLimit"):
        raise QldDataError("Ambiguous geographic match")
    return features[0] if features else None


def parse_forecast(
    payload: Any, *, now: datetime, max_age: timedelta = timedelta(hours=36)
) -> dict[str, Any]:
    """Parse the fire danger polygon covering the monitored point.

    ``covered`` is False only for a valid zero-feature spatial query. It is
    unknown on a failed request (handled by the provider).
    """
    row = _one_feature(payload)
    if row is None:
        return {"covered": False, "health": "unavailable", "error": "out_of_coverage"}

    district = row.get("Area_Name")
    if not isinstance(district, str) or not district.strip():
        raise QldDataError("Fire weather district missing")

    published = _timestamp(row.get("FMETimeStamp"))
    if published is None:
        raise QldDataError("Forecast source timestamp missing")
    now_utc = now.astimezone(UTC)
    age = now_utc - published
    if age < -timedelta(hours=2):
        raise QldDataError("Forecast source timestamp is in the future")

    by_date: dict[date, str] = {}
    for n in range(1, 5):
        raw_date, rating = row.get(f"Date{n}"), row.get(f"Day{n}")
        if raw_date is None and (rating is None or rating == ""):
            continue
        stamp = _timestamp(raw_date)
        if stamp is None:
            raise QldDataError("Forecast rating has no date")
        local_day = stamp.astimezone(AEST).date()
        if rating not in VALID_RATINGS:
            raise QldDataError("Unexpected AFDRS rating")
        if local_day in by_date:
            raise QldDataError("Duplicate fire danger forecast date")
        by_date[local_day] = rating

    if not by_date:
        raise QldDataError("No dated fire danger ratings")
    today = now.astimezone(AEST).date()
    forecast = [
        {"date": (today + timedelta(days=n)).isoformat(),
         "rating": by_date.get(today + timedelta(days=n), "Unknown"),
         "available": (today + timedelta(days=n)) in by_date and age <= max_age}
        for n in range(4)
    ]
    return {
        "covered": True,
        "health": "fresh" if age <= max_age else "stale",
        "district": district.strip(),
        "source_updated_at": published.isoformat(),
        "forecast": forecast,
        "error": None if age <= max_age else "source_timestamp_stale",
    }


def parse_local_fire_ban(payload: Any) -> dict[str, Any]:
    """Parse explicit QFD fire-ban states; never derive No Ban from zero rows."""
    row = _one_feature(payload)
    if row is None:
        raise QldDataError("No council fire-ban polygon matched location")
    council, raw = row.get("SHIRE_NAME"), row.get("HASFIREBAN")
    if not isinstance(council, str) or not council.strip():
        raise QldDataError("Council name missing")
    if raw not in ("Fire Ban", "No Fire Ban"):
        raise QldDataError("Unexpected fire-ban state")
    link = row.get("Link")
    return {
        "state": raw == "Fire Ban",
        "raw_status": raw,
        "lga": council.strip(),
        "effective_from": _iso(_timestamp(row.get("DATE_FROM"))),
        "effective_to": _iso(_timestamp(row.get("DATE_TO"))),
        "record_updated_at": _iso(_timestamp(row.get("FMETimestamp"))),
        "declaration_url": link if isinstance(link, str) and link.startswith("https://") else None,
    }


def parse_emergency(payload: Any) -> dict[str, Any]:
    """Parse reported emergency status. Positive 'Yes' needs field validation."""
    row = _one_feature(payload)
    if row is None:
        raise QldDataError("No emergency polygon matched location")
    lga, raw = row.get("LGA_Name"), row.get("InStateOfEmergency")
    if not isinstance(lga, str) or not lga.strip():
        raise QldDataError("Emergency LGA name missing")
    if raw not in ("Yes", "No"):
        raise QldDataError("Unexpected State of Emergency status")
    return {
        "state": raw == "Yes",
        "raw_status": raw,
        "lga": lga.strip(),
        "lga_code": row.get("LGA_code"),
    }


def danger_from_forecast(forecast: dict[str, Any]) -> dict[str, Any]:
    """Build the existing coordinator danger contract without NSW ban semantics."""
    days = list(forecast.get("forecast") or [])

    def day(index: int) -> dict[str, Any]:
        info = days[index] if index < len(days) else {}
        return {
            "date": info.get("date"),
            "rating": info.get("rating", "Unknown"),
            "available": bool(info.get("available")),
            "fbi": None,
            "total_fire_ban": None,
            "issued_at": forecast.get("source_updated_at"),
            "rating_source": "QFD/BOM ArcGIS FDR",
            "fbi_source": None,
            "retained": not bool(info.get("available")),
        }

    return {
        "district": forecast.get("district"),
        "today": day(0),
        "tomorrow": day(1),
        "forecast": days,
        "rfs_issued_at": None,
        "bom_issued_at": forecast.get("source_updated_at"),
        "source_note": (
            "Queensland QFD/BOM forecast; fire bans are separate legal declarations. "
            "Unmatched or stale ratings are unavailable."
        ),
    }


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None
