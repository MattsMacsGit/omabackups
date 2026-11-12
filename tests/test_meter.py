"""The honest bar's numbers (D49): speed, time left only when it can be
trusted, stuck after 3 minutes, never past 99% until rsync has finished."""

from omabackups.backup.meter import Meter, rounded, size


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def test_speed_is_the_last_minute():
    clock = Clock()
    m = Meter(10_000_000_000, clock=clock)
    sent = 0
    for second in range(1, 121):
        clock.now += 1
        sent += 1_000_000 if second <= 60 else 5_000_000  # 1 MB/s, then 5 MB/s
        m.update(sent=sent)
    assert 4_900_000 <= m.speed() <= 5_100_000            # the last minute, not the average


def test_time_left_waits_until_it_can_be_trusted():
    clock = Clock()
    m = Meter(1_000_000_000, clock=clock)
    for second in range(1, 170):
        clock.now += 1
        m.update(sent=second * 1_000_000)
    assert m.left() is None                              # under 3 minutes of sending
    for second in range(170, 400):
        clock.now += 1
        m.update(sent=second * 1_000_000)
    assert 590 <= m.left() <= 610                        # 600 MB to go at 1 MB/s


def test_stuck_after_3_minutes_of_nothing():
    clock = Clock()
    m = Meter(100, clock=clock)
    m.update(sent=10)
    clock.now += 179
    m.update(sent=10)
    assert not m.stuck()
    clock.now += 2
    m.update(sent=10)
    assert m.stuck()


def test_a_finished_file_counts_as_moving():
    clock = Clock()
    m = Meter(100, clock=clock)
    clock.now += 170
    m.update(sent=0, ticks=1)
    clock.now += 170
    assert not m.stuck()


def test_never_backwards_and_never_100_before_the_end():
    m = Meter(100)
    m.update(sent=100)
    m.update(sent=50)
    assert m.sent == 100 and m.fraction() == 0.99


def test_words():
    assert rounded(None) == ""
    assert rounded(30) == "less than a minute"
    assert rounded(7 * 60) == "about 7 min"
    assert rounded(23 * 60) == "about 25 min"
    assert rounded(3 * 3600 + 17 * 60) == "about 3 h 20 min"
    assert size(12_400_000_000) == "12.4 GB" and size(310_000_000_000) == "310 GB"
