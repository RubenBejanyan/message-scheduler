import pytest

from message_scheduler.scheduler import parse_interval

# ── interval (Nm / Nh / Nd) ──────────────────────────────────────────────────

@pytest.mark.parametrize("text,expected_seconds", [
    ("30m", 1800),
    ("1m", 60),
    ("120m", 7200),
    ("2h", 7200),
    ("24h", 86400),
    ("1d", 86400),
    ("7d", 604800),
])
def test_interval_valid(text: str, expected_seconds: int) -> None:
    result = parse_interval(text)
    assert result is not None
    kind, value, _ = result
    assert kind == "interval"
    assert value == str(expected_seconds)


def test_interval_returns_label_minutes() -> None:
    _, _, label = parse_interval("45m")  # type: ignore[misc]
    assert "45" in label and "minute" in label


def test_interval_returns_label_hours() -> None:
    _, _, label = parse_interval("3h")  # type: ignore[misc]
    assert "3" in label and "hour" in label


def test_interval_returns_label_days() -> None:
    _, _, label = parse_interval("2d")  # type: ignore[misc]
    assert "2" in label and "day" in label


@pytest.mark.parametrize("text", [
    "0m", "-1h", "0d", "-5m",
])
def test_interval_zero_or_negative_returns_none(text: str) -> None:
    assert parse_interval(text) is None


@pytest.mark.parametrize("text", [
    "xm", "1.5h", "abcd", "m", "h", "d",
])
def test_interval_non_integer_returns_none(text: str) -> None:
    assert parse_interval(text) is None


# ── daily (cron) ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("text,expected_value", [
    ("daily 09:00", "09:00"),
    ("daily 00:00", "00:00"),
    ("daily 23:59", "23:59"),
    ("daily 9:05", "09:05"),
])
def test_daily_valid(text: str, expected_value: str) -> None:
    result = parse_interval(text)
    assert result is not None
    kind, value, label = result
    assert kind == "cron"
    assert value == expected_value
    assert "daily" in label


@pytest.mark.parametrize("text", [
    "daily 24:00",
    "daily 12:60",
    "daily 99:99",
    "daily abc",
    "daily 9",
    "daily",
])
def test_daily_invalid_returns_none(text: str) -> None:
    assert parse_interval(text) is None


# ── window ────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("text,expected_value", [
    ("window 08:00-09:00", "08:00-09:00"),
    ("window 00:00-23:59", "00:00-23:59"),
    ("window 15:15-15:50", "15:15-15:50"),
])
def test_window_valid(text: str, expected_value: str) -> None:
    result = parse_interval(text)
    assert result is not None
    kind, value, label = result
    assert kind == "window"
    assert value == expected_value
    assert "between" in label


def test_window_end_before_start_returns_none() -> None:
    assert parse_interval("window 10:00-09:00") is None


def test_window_equal_times_returns_none() -> None:
    assert parse_interval("window 10:00-10:00") is None


@pytest.mark.parametrize("text", [
    "window 25:00-26:00",
    "window 10:61-11:00",
    "window abc-def",
    "window 10:00",
    "window",
])
def test_window_invalid_returns_none(text: str) -> None:
    assert parse_interval(text) is None


# ── garbage ───────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("text", ["", "   ", "???", "1", "every day", "5 minutes"])
def test_unknown_format_returns_none(text: str) -> None:
    assert parse_interval(text) is None
