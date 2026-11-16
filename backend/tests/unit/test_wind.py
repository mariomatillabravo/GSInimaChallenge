"""Unit tests for the wind-energy formulas and the choice of metrics (pure functions)."""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.core.exceptions import InvalidParameterError
from app.domain.measurements import Aggregation, MeasurementType
from app.domain.wind import (
    METRIC_FIELDS,
    MetricSet,
    WindMetric,
    air_density,
    cubic_mean,
    power_density,
    select_metrics,
)

ALL_TYPES = tuple(MeasurementType)


class TestFormulas:
    def test_air_density_of_dry_air(self) -> None:
        # 100,000 Pa / (287.05 J/(kg·K) x 273.15 K) = 1.27538... kg/m³
        assert air_density(1000.0, 0.0) == pytest.approx(1.27538, abs=1e-5)

    def test_colder_or_denser_air_is_heavier(self) -> None:
        assert air_density(1000.0, -20.0) > air_density(1000.0, 0.0)
        assert air_density(1010.0, 0.0) > air_density(1000.0, 0.0)

    def test_power_density_grows_with_the_cube_of_the_speed(self) -> None:
        assert power_density(1.2, 10.0) == pytest.approx(600.0)
        assert power_density(1.2, 20.0) == pytest.approx(8 * 600.0)

    def test_cubic_mean_weights_strong_winds(self) -> None:
        assert cubic_mean([1.0, 2.0, 3.0]) == pytest.approx(12 ** (1 / 3))  # (1 + 8 + 27) / 3
        assert cubic_mean([0.0, 10.0]) == pytest.approx(500 ** (1 / 3))  # about 7.94, not 5
        assert cubic_mean([4.0]) == pytest.approx(4.0)

    def test_cubic_mean_of_nothing_is_none(self) -> None:
        assert cubic_mean([]) is None


@given(st.lists(st.floats(min_value=0, max_value=60), min_size=1, max_size=50))
def test_cubic_mean_is_never_below_the_arithmetic_mean(speeds: list[float]) -> None:
    result = cubic_mean(speeds)

    assert result is not None
    assert result >= sum(speeds) / len(speeds) - 1e-9
    assert result <= max(speeds) + 1e-9


class TestSelectMetrics:
    def test_no_option_means_no_metrics(self) -> None:
        assert select_metrics(None, Aggregation.HOURLY, ALL_TYPES) == ()

    def test_all_metrics_when_every_type_is_requested(self) -> None:
        assert select_metrics(MetricSet.EXTENDED, Aggregation.DAILY, ALL_TYPES) == tuple(WindMetric)

    def test_only_the_metrics_whose_inputs_are_requested(self) -> None:
        assert select_metrics(MetricSet.EXTENDED, Aggregation.HOURLY, [MeasurementType.SPEED]) == (
            WindMetric.SPEED_CUBIC_MEAN,
            WindMetric.SPEED_MAX,
        )
        assert select_metrics(
            MetricSet.EXTENDED,
            Aggregation.MONTHLY,
            [MeasurementType.TEMPERATURE, MeasurementType.PRESSURE],
        ) == (WindMetric.TEMPERATURE_MIN, WindMetric.TEMPERATURE_MAX, WindMetric.AIR_DENSITY)

    def test_power_density_needs_the_three_measurements(self) -> None:
        assert METRIC_FIELDS[WindMetric.POWER_DENSITY].inputs == frozenset(MeasurementType)

    def test_raw_records_are_rejected(self) -> None:
        with pytest.raises(InvalidParameterError) as caught:
            select_metrics(MetricSet.EXTENDED, Aggregation.NONE, ALL_TYPES)

        assert caught.value.parameter == "metrics"
        assert "choose an aggregation level" in caught.value.message


def test_every_metric_has_a_unique_key_and_a_unit() -> None:
    keys = [spec.key for spec in METRIC_FIELDS.values()]

    assert len(set(keys)) == len(WindMetric) == len(keys)
    assert all(spec.unit for spec in METRIC_FIELDS.values())
