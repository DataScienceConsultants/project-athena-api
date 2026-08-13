"""Read-only delivery helpers for prepared Athena research artifacts."""

from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any


class ResearchBundleUnavailableError(RuntimeError):
    """Raised when the prepared global research bundle is unavailable or invalid."""


class ResearchArtifactService:
    """Serve prepared Athena global-research artifacts without recomputing science."""

    def __init__(self, bundle_path: str | Path) -> None:
        self.bundle_path = Path(bundle_path)

    def summary(self) -> dict[str, Any]:
        metadata = self._required_json_object("metadata.json")
        availability = {
            "catalog": (self.bundle_path / "catalog.csv").is_file(),
            "fault_associations": (self.bundle_path / "fault_associations.csv").is_file(),
            "fault_geometry": (self.bundle_path / "faults.geojson").is_file(),
            "plate_boundaries": (self.bundle_path / "plate_boundaries.geojson").is_file(),
            "plate_connections": (self.bundle_path / "event_plate_context.csv").is_file(),
            "sequences": (self.bundle_path / "sequences.json").is_file(),
        }
        return {
            **metadata,
            "availability": availability,
            "delivery_mode": "prepared_artifacts",
            "report_is_nonpredictive": True,
        }

    def earthquakes(
        self,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        minimum_magnitude: float = 6.0,
        min_latitude: float | None = None,
        max_latitude: float | None = None,
        min_longitude: float | None = None,
        max_longitude: float | None = None,
        offset: int = 0,
        limit: int = 5000,
    ) -> dict[str, Any]:
        rows = self._required_csv("catalog.csv")
        items: list[dict[str, Any]] = []
        for row in rows:
            event = self._event_payload(row)
            magnitude = event["magnitude"]
            if magnitude is None or magnitude < minimum_magnitude:
                continue
            event_time = self._parse_time(event["time"])
            if start is not None and event_time < start:
                continue
            if end is not None and event_time >= end:
                continue
            longitude, latitude = event["coordinates"]
            if min_latitude is not None and latitude < min_latitude:
                continue
            if max_latitude is not None and latitude > max_latitude:
                continue
            if not self._longitude_matches(longitude, min_longitude, max_longitude):
                continue
            items.append(event)

        total = len(items)
        page = items[offset : offset + limit]
        return {
            "items": page,
            "filtered_count": total,
            "returned_count": len(page),
            "offset": offset,
            "limit": limit,
            "truncated": offset + len(page) < total,
            "report_is_nonpredictive": True,
        }

    def faults(self) -> dict[str, Any]:
        path = self.bundle_path / "faults.geojson"
        if not path.is_file():
            return self._unavailable_feature_collection(
                "Prepared fault geometry is not present in this research bundle."
            )
        payload = self._json(path)
        if not isinstance(payload, dict) or payload.get("type") != "FeatureCollection":
            raise ResearchBundleUnavailableError(
                "faults.geojson must be a GeoJSON FeatureCollection"
            )
        return {
            **payload,
            "available": True,
            "report_is_nonpredictive": True,
        }

    def fault(self, fault_id: str) -> dict[str, Any] | None:
        geometry: dict[str, Any] | None = None
        faults = self.faults()
        for feature in faults.get("features", []):
            properties = feature.get("properties") or {}
            candidate = properties.get("fault_id") or properties.get("id")
            if str(candidate) == fault_id:
                geometry = feature
                break

        associations = [
            item for item in self.connections()["items"] if item["fault_id"] == fault_id
        ]
        if geometry is None and not associations:
            return None
        return {
            "fault_id": fault_id,
            "feature": geometry,
            "associations": associations,
            "association_count": len(associations),
            "geometry_available": geometry is not None,
            "report_is_nonpredictive": True,
        }

    def plate_boundaries(self) -> dict[str, Any]:
        path = self.bundle_path / "plate_boundaries.geojson"
        if not path.is_file():
            return self._unavailable_feature_collection(
                "Prepared plate-boundary geometry is not present in this research bundle."
            )
        payload = self._json(path)
        if not isinstance(payload, dict) or payload.get("type") != "FeatureCollection":
            raise ResearchBundleUnavailableError(
                "plate_boundaries.geojson must be a GeoJSON FeatureCollection"
            )
        return {
            **payload,
            "available": True,
            "report_is_nonpredictive": True,
        }

    def sequences(self) -> dict[str, Any]:
        path = self.bundle_path / "sequences.json"
        if not path.is_file():
            return {
                "items": [],
                "available": False,
                "reason": "Prepared sequence artifacts are not present in this research bundle.",
                "report_is_nonpredictive": True,
            }
        payload = self._json(path)
        if isinstance(payload, list):
            items = payload
        elif isinstance(payload, dict) and isinstance(payload.get("sequences"), list):
            items = payload["sequences"]
        else:
            raise ResearchBundleUnavailableError(
                "sequences.json must be a list or an object containing a sequences list"
            )
        return {
            "items": items,
            "available": True,
            "report_is_nonpredictive": True,
        }

    def sequence(self, sequence_id: str) -> dict[str, Any] | None:
        for item in self.sequences()["items"]:
            if str(item.get("id")) == sequence_id:
                return item
        return None

    def connections(self) -> dict[str, Any]:
        path = self.bundle_path / "fault_associations.csv"
        if not path.is_file():
            return {
                "items": [],
                "available": False,
                "reason": "Prepared event-to-fault associations are not present in this bundle.",
                "report_is_nonpredictive": True,
            }
        items = []
        for row in self._csv(path):
            items.append(
                {
                    "event_id": row["event_id"],
                    "fault_id": row["fault_id"],
                    "fault_name": row.get("fault_name") or None,
                    "distance_km": self._float_or_none(row.get("distance_km")),
                    "fault_source": row.get("fault_source") or None,
                    "relationship": "nearest_mapped_active_fault_context",
                }
            )
        return {
            "items": items,
            "available": True,
            "report_is_nonpredictive": True,
            "semantics": (
                "Geographic context only. Nearest mapped fault association is not causal "
                "attribution and does not imply future earthquake probability."
            ),
        }

    def plate_connections(self) -> dict[str, Any]:
        path = self.bundle_path / "event_plate_context.csv"
        if not path.is_file():
            return {
                "items": [],
                "available": False,
                "reason": (
                    "Prepared event-to-plate-boundary associations are not present in this bundle."
                ),
                "report_is_nonpredictive": True,
            }
        items = []
        for row in self._csv(path):
            items.append(
                {
                    "event_id": row["event_id"],
                    "step_id": row["step_id"],
                    "boundary_id": row["boundary_id"],
                    "left_plate": row["left_plate"],
                    "right_plate": row["right_plate"],
                    "boundary_class": row["boundary_class"],
                    "polarity": row.get("polarity") or None,
                    "distance_km": self._float_or_none(row.get("distance_km")),
                    "source": row.get("source") or None,
                    "relationship": "nearest_mapped_plate_boundary_context",
                }
            )
        return {
            "items": items,
            "available": True,
            "report_is_nonpredictive": True,
            "semantics": (
                "Tectonic context only. Nearest mapped PB2002 boundary association, adjacent "
                "plate identifiers, and source-defined boundary class are not causal attribution, "
                "stress-transfer calculations, or future-earthquake probabilities."
            ),
        }

    def region(self, region_key: str) -> dict[str, Any] | None:
        summary = self.summary()
        accepted = {"global", str(summary.get("profile_id", ""))}
        if region_key not in accepted:
            return None
        return {
            "region_key": "global",
            "name": "Global M6+ research cohort",
            "summary": summary,
            "report_is_nonpredictive": True,
        }

    def _required_json_object(self, name: str) -> dict[str, Any]:
        path = self.bundle_path / name
        if not path.is_file():
            raise ResearchBundleUnavailableError(f"Prepared research artifact is missing: {name}")
        payload = self._json(path)
        if not isinstance(payload, dict):
            raise ResearchBundleUnavailableError(
                f"Prepared research artifact must be an object: {name}"
            )
        return payload

    def _required_csv(self, name: str) -> list[dict[str, str]]:
        path = self.bundle_path / name
        if not path.is_file():
            raise ResearchBundleUnavailableError(f"Prepared research artifact is missing: {name}")
        return self._csv(path)

    @staticmethod
    def _json(path: Path) -> Any:
        try:
            with path.open("r", encoding="utf-8") as source:
                return json.load(source)
        except (OSError, json.JSONDecodeError) as exc:
            raise ResearchBundleUnavailableError(
                f"Could not read prepared artifact: {path.name}"
            ) from exc

    @staticmethod
    def _csv(path: Path) -> list[dict[str, str]]:
        try:
            with path.open("r", encoding="utf-8", newline="") as source:
                return list(csv.DictReader(source))
        except OSError as exc:
            raise ResearchBundleUnavailableError(
                f"Could not read prepared artifact: {path.name}"
            ) from exc

    @classmethod
    def _event_payload(cls, row: dict[str, str]) -> dict[str, Any]:
        longitude = cls._required_float(row, "longitude")
        latitude = cls._required_float(row, "latitude")
        return {
            "id": row.get("event_id") or "",
            "magnitude": cls._float_or_none(row.get("magnitude")),
            "time": row.get("time") or "",
            "depth": cls._float_or_none(row.get("depth")),
            "region": row.get("place") or "Unavailable",
            "coordinates": [longitude, latitude],
            "magnitude_type": row.get("magnitude_type") or None,
            "status": row.get("status") or None,
            "event_type": row.get("event_type") or None,
            "source": row.get("source") or "USGS",
            "updated_at": row.get("updated_at") or None,
            "athena_score": None,
            "sequence_id": None,
            "sequence_position": None,
        }

    @staticmethod
    def _required_float(row: dict[str, str], name: str) -> float:
        value = ResearchArtifactService._float_or_none(row.get(name))
        if value is None:
            raise ResearchBundleUnavailableError(f"Catalog row is missing numeric {name}")
        return value

    @staticmethod
    def _float_or_none(value: str | None) -> float | None:
        if value is None or not value.strip():
            return None
        try:
            return float(value)
        except ValueError as exc:
            raise ResearchBundleUnavailableError(
                f"Invalid numeric research artifact value: {value}"
            ) from exc

    @staticmethod
    def _parse_time(value: str) -> datetime:
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ResearchBundleUnavailableError(f"Invalid catalog timestamp: {value}") from exc

    @staticmethod
    def _longitude_matches(
        longitude: float,
        minimum: float | None,
        maximum: float | None,
    ) -> bool:
        if minimum is None and maximum is None:
            return True
        if minimum is None:
            return longitude <= maximum
        if maximum is None:
            return longitude >= minimum
        if minimum <= maximum:
            return minimum <= longitude <= maximum
        return longitude >= minimum or longitude <= maximum

    @staticmethod
    def _unavailable_feature_collection(reason: str) -> dict[str, Any]:
        return {
            "type": "FeatureCollection",
            "features": [],
            "available": False,
            "reason": reason,
            "report_is_nonpredictive": True,
        }
