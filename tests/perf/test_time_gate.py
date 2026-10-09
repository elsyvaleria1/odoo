import time

import pytest

from ._bench import ServerClock, calibration_ms, measure, run_delay
from .conftest import CALIBRATION_KEY, _check

FLOORS = {
    CALIBRATION_KEY: 20.0,
    "scenario": {"statements": 4, "non_sql_ms": 10.0},
}
READINGS = {
    "statements": 4,
    "statements_min": 4,
    "statements_max": 4,
    "non_sql_ms": 30.0,
}


def test_a_slow_reading_on_a_machine_at_floor_speed_is_red():
    with pytest.raises(AssertionError, match=r"non_sql_ms reads 30\.0"):
        _check(
            "scenario",
            READINGS,
            counts_only=False,
            calibration=20.0,
            floors_data=FLOORS,
        )


def test_a_slowed_machine_leaves_time_unjudged_and_counts_exact():
    assert not _check(
        "scenario",
        READINGS,
        counts_only=False,
        calibration=40.0,
        floors_data=FLOORS,
    )
    with pytest.raises(AssertionError, match="an exact ratchet"):
        _check(
            "scenario",
            {**READINGS, "statements": 5, "statements_max": 5},
            counts_only=False,
            calibration=40.0,
            floors_data=FLOORS,
        )


def test_a_reading_within_tolerance_is_judged_and_green():
    assert _check(
        "scenario",
        {**READINGS, "non_sql_ms": 12.0},
        counts_only=False,
        calibration=24.0,
        floors_data=FLOORS,
    )


def test_a_flow_that_waited_for_a_cpu_in_every_round_leaves_time_unjudged():
    assert not _check(
        "scenario",
        {**READINGS, "rounds": 3, "rounds_contended": 3},
        counts_only=False,
        calibration=20.0,
        floors_data=FLOORS,
    )


def test_a_flow_with_one_clean_round_is_judged():
    with pytest.raises(AssertionError, match=r"non_sql_ms reads 30\.0"):
        _check(
            "scenario",
            {**READINGS, "rounds": 3, "rounds_contended": 2},
            counts_only=False,
            calibration=20.0,
            floors_data=FLOORS,
        )


class _Counter:
    count = chars = 0
    seconds = 0.0

    def reset(self):
        self.seconds = 0.0


def test_a_round_that_waited_for_a_cpu_is_not_the_reading():
    # three rounds of 5, 2 and 9 ms; the 2 ms one spent 1 ms on the run queue,
    # so it is not the floor's reading even though it is the fastest
    ticks = iter([0.0, 0.005, 1.0, 1.002, 2.0, 2.009])
    waits = iter([0.0, 0.0, 0.0, 0.001, 0.001, 0.001])
    readings = measure(
        lambda: None,
        _Counter(),
        repeat=1,
        rounds=3,
        clock=lambda: next(ticks),
        waited=lambda: next(waits),
    )
    assert readings["wall_ms"] == 5.0
    assert readings["rounds"] == 3
    assert readings["rounds_contended"] == 1


class _WaitingCounter(_Counter):
    sql_wait = 0.0

    def reset(self):
        super().reset()
        self.sql_wait = 0.0


def test_a_wait_inside_the_statements_does_not_contend_the_round():
    # one round of 5 ms, 3 of them SQL; it waited 1 ms for a CPU, all of it
    # on the wake-up after its statements, which the residual does not hold
    counter = _WaitingCounter()
    ticks = iter([0.0, 0.005])
    waits = iter([0.0, 0.001])

    def fn():
        counter.seconds = 0.003
        counter.sql_wait = 0.001

    readings = measure(
        fn,
        counter,
        repeat=1,
        rounds=1,
        clock=lambda: next(ticks),
        waited=lambda: next(waits),
    )
    assert readings["rounds_contended"] == 0


def test_the_run_delay_is_a_duration():
    assert run_delay() >= 0.0


def test_the_calibration_is_a_positive_duration():
    assert calibration_ms(runs=2) > 0


class _Server:
    def outer(self):
        time.sleep(0.02)
        return self.inner()

    def inner(self):
        time.sleep(0.02)
        return "answer"


def test_the_server_clock_counts_only_the_outermost_call_and_unwraps():
    clock = ServerClock()
    original_outer = _Server.__dict__["outer"]
    original_inner = _Server.__dict__["inner"]
    clock.wrap(_Server, "outer", "inner")
    try:
        assert _Server().outer() == "answer"
    finally:
        clock.unwrap()
    assert 0.035 <= clock() < 0.08
    assert _Server.__dict__["outer"] is original_outer
    assert _Server.__dict__["inner"] is original_inner


SIZED = {"scenario": {"statements": 4, "sql_chars": 1000}}


def test_a_flow_sending_more_sql_text_is_red_on_every_machine():
    with pytest.raises(AssertionError, match="sends more SQL text"):
        _check(
            "scenario",
            {**READINGS, "sql_chars": 2500},
            counts_only=True,
            floors_data=SIZED,
        )


def test_a_flow_sending_less_sql_text_asks_for_its_floor():
    with pytest.raises(AssertionError, match="lower the floor"):
        _check(
            "scenario",
            {**READINGS, "sql_chars": 800},
            counts_only=True,
            floors_data=SIZED,
        )


def test_sql_text_within_its_band_is_green():
    _check(
        "scenario",
        {**READINGS, "sql_chars": 1080},
        counts_only=True,
        floors_data=SIZED,
    )
