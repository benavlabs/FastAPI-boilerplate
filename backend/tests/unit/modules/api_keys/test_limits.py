"""The windows a key's ``usage_limits`` are counted under, the order and the arithmetic."""

from src.modules.api_keys.limits import counted_shortest_first, time_left, window_stamped


def test_the_windows_are_counted_shortest_first_whatever_order_they_were_written_in():
    """The first window a request fills refuses it, so a longer one must never be counted first.

    The counts here fall as the windows grow, which nothing forbids: a stored limit is
    whatever its owner wrote, so the counts can never stand in for the window lengths.
    """
    written = {"requests_per_day": 10, "requests_per_hour": 50, "requests_per_minute": 100}

    counted = counted_shortest_first(written)

    assert counted == [("requests_per_minute", 100), ("requests_per_hour", 50), ("requests_per_day", 10)]


def test_a_window_nothing_counts_is_left_out():
    """A limit stored before this vocabulary existed counts for nothing and refuses nothing."""
    counted = counted_shortest_first({"requests_per_fortnight": 1, "requests_per_minute": 2})

    assert counted == [("requests_per_minute", 2)]


def test_a_counter_is_read_under_the_window_running_now():
    """The limiter counts under a key of this shape, so reading one costs the key nothing.

    A minute window and the fifth second of it: the window itself started at 120.
    """
    assert window_stamped("api_key:7:requests_per_minute", 60, 125) == "api_key:7:requests_per_minute:120"


def test_what_is_left_of_a_window_is_the_time_until_the_next_one_starts():
    """``Retry-After`` carries it, so the time the window has already spent would come back early."""
    assert time_left(60, 125) == 55
