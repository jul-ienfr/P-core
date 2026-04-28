from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, Mapping


@dataclass(frozen=True, slots=True)
class LeadTimeBucket:
    start_hours: float
    end_hours: float

    def __contains__(self, lead_time_hours: object) -> bool:
        try:
            value = float(lead_time_hours)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return False
        return self.start_hours <= value < self.end_hours


@dataclass(frozen=True, slots=True)
class WeatherCalibrationSample:
    city: str
    station_code: str
    measurement_kind: str
    lead_time_hours: float
    forecast_value: float
    observed_value: float


@dataclass(frozen=True, slots=True)
class RmseEstimate:
    rmse: float
    count: int


CalibrationGroupKey = tuple[str | None, str | None, str | None, LeadTimeBucket | None]


@dataclass(frozen=True, slots=True)
class GroupedRmsePolicy:
    estimates: Mapping[CalibrationGroupKey, RmseEstimate]
    minimum_sigma: float = 0.6
    default_sigma: float = 0.0

    def sigma(
        self,
        dispersion: float | None,
        lead_time_hours: float | None = None,
        *,
        city: str | None = None,
        station_code: str | None = None,
        measurement_kind: str | None = None,
    ) -> float:
        observed_sigma = max(float(dispersion or 0.0), 0.0)
        rmse = self._rmse_for(
            city=city,
            station_code=station_code,
            measurement_kind=measurement_kind,
            lead_time_hours=lead_time_hours,
        )
        widened = math.sqrt((observed_sigma * observed_sigma) + (rmse * rmse))
        return round(max(widened, self.minimum_sigma), 4)

    def _rmse_for(
        self,
        *,
        city: str | None,
        station_code: str | None,
        measurement_kind: str | None,
        lead_time_hours: float | None,
    ) -> float:
        normalized_city = _normalize(city)
        normalized_station = _normalize(station_code)
        normalized_measurement = _normalize(measurement_kind)
        bucket = _bucket_for_lead_time(self.estimates, lead_time_hours)

        key = (normalized_city, normalized_station, normalized_measurement, bucket)
        estimate = self.estimates.get(key)
        if estimate is not None:
            return estimate.rmse

        global_estimate = self.estimates.get((None, None, None, None))
        if global_estimate is not None:
            return global_estimate.rmse

        return max(float(self.default_sigma), 0.0)


def load_calibration_samples(
    rows: Iterable[WeatherCalibrationSample | Mapping[str, object]],
    *,
    city: str | None = None,
    station_code: str | None = None,
    measurement_kind: str | None = None,
    lead_time_bucket: LeadTimeBucket | None = None,
) -> list[WeatherCalibrationSample]:
    samples = [_coerce_sample(row) for row in rows]
    return [
        sample
        for sample in samples
        if _matches(sample, city=city, station_code=station_code, measurement_kind=measurement_kind, lead_time_bucket=lead_time_bucket)
    ]


def group_rmse_estimates(
    samples: Iterable[WeatherCalibrationSample],
    *,
    lead_time_buckets: Iterable[LeadTimeBucket],
) -> dict[CalibrationGroupKey, RmseEstimate]:
    buckets = tuple(lead_time_buckets)
    errors_by_group: dict[CalibrationGroupKey, list[float]] = {}
    global_errors: list[float] = []

    for sample in samples:
        error = float(sample.forecast_value) - float(sample.observed_value)
        global_errors.append(error)
        bucket = _bucket_for_value(buckets, sample.lead_time_hours)
        if bucket is None:
            continue
        key = (
            _normalize(sample.city),
            _normalize(sample.station_code),
            _normalize(sample.measurement_kind),
            bucket,
        )
        errors_by_group.setdefault(key, []).append(error)

    estimates = {key: _estimate(errors) for key, errors in errors_by_group.items()}
    if global_errors:
        estimates[(None, None, None, None)] = _estimate(global_errors)
    return estimates


def _coerce_sample(row: WeatherCalibrationSample | Mapping[str, object]) -> WeatherCalibrationSample:
    if isinstance(row, WeatherCalibrationSample):
        return row
    return WeatherCalibrationSample(
        city=str(_get(row, "city")).strip(),
        station_code=str(_get(row, "station_code", "station")).strip(),
        measurement_kind=_normalize_required(_get(row, "measurement_kind", "measurement")),
        lead_time_hours=float(_get(row, "lead_time_hours", "lead_hours")),
        forecast_value=float(_get(row, "forecast_value", "forecast")),
        observed_value=float(_get(row, "observed_value", "observed")),
    )


def _get(row: Mapping[str, object], *names: str) -> object:
    for name in names:
        if name in row and row[name] not in (None, ""):
            return row[name]
    raise ValueError(f"missing required calibration field: {names[0]}")


def _matches(
    sample: WeatherCalibrationSample,
    *,
    city: str | None,
    station_code: str | None,
    measurement_kind: str | None,
    lead_time_bucket: LeadTimeBucket | None,
) -> bool:
    if city is not None and _normalize(sample.city) != _normalize(city):
        return False
    if station_code is not None and _normalize(sample.station_code) != _normalize(station_code):
        return False
    if measurement_kind is not None and _normalize(sample.measurement_kind) != _normalize(measurement_kind):
        return False
    if lead_time_bucket is not None and sample.lead_time_hours not in lead_time_bucket:
        return False
    return True


def _bucket_for_value(buckets: Iterable[LeadTimeBucket], lead_time_hours: float | None) -> LeadTimeBucket | None:
    for bucket in buckets:
        if lead_time_hours in bucket:
            return bucket
    return None


def _bucket_for_lead_time(estimates: Mapping[CalibrationGroupKey, RmseEstimate], lead_time_hours: float | None) -> LeadTimeBucket | None:
    if lead_time_hours is None:
        return None
    buckets = [key[3] for key in estimates if key[3] is not None]
    return _bucket_for_value(buckets, lead_time_hours)


def _estimate(errors: list[float]) -> RmseEstimate:
    rmse = math.sqrt(sum(error * error for error in errors) / len(errors))
    return RmseEstimate(rmse=round(rmse, 4), count=len(errors))


def _normalize(value: str | None) -> str | None:
    if value is None:
        return None
    return str(value).strip().lower()


def _normalize_required(value: object) -> str:
    return str(value).strip().lower()
