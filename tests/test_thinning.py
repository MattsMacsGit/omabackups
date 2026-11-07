from datetime import datetime, timedelta

from omabackups.backup.thinning import to_delete

NOW = datetime(2026, 11, 7, 12, 0)


def name(dt: datetime, line: str = "001") -> str:
    return f"{line}-{dt:%Y-%m-%d-%H%M}"


def hourly(hours: int, line: str = "001") -> list[str]:
    return [name(NOW - timedelta(hours=h), line) for h in range(hours)]


def test_the_last_day_is_all_kept():
    assert to_delete(hourly(24), NOW) == []


def test_one_a_day_for_a_month():
    names = hourly(24 * 10)
    gone = set(to_delete(names, NOW))
    left = [n for n in names if n not in gone]
    older = [n for n in left if NOW - datetime.strptime(n[4:], "%Y-%m-%d-%H%M") > timedelta(hours=24)]
    days = [n[4:14] for n in older]
    assert len(days) == len(set(days))          # at most one per day
    assert len(set(days)) >= 9                  # and every day still has one
    # The one kept per day is that day's newest.
    for n in older:
        same_day = [m for m in names if m[4:14] == n[4:14]
                    and NOW - datetime.strptime(m[4:], "%Y-%m-%d-%H%M") > timedelta(hours=24)]
        assert n == max(same_day)


def test_then_one_a_week():
    names = [name(NOW - timedelta(days=d)) for d in range(0, 120)]
    gone = set(to_delete(names, NOW))
    old = [n for n in names if n not in gone
           and NOW - datetime.strptime(n[4:], "%Y-%m-%d-%H%M") > timedelta(days=30)]
    weeks = [datetime.strptime(n[4:], "%Y-%m-%d-%H%M").isocalendar()[:2] for n in old]
    assert len(weeks) == len(set(weeks))


def test_never_the_newest_and_never_a_kept_one():
    # Two from the same old day: only one of them can stay...
    names = [name(NOW - timedelta(days=200, hours=1)), name(NOW - timedelta(days=200)), name(NOW)]
    assert to_delete(names, NOW) == [names[0]]                 # ...and it's that day's newest
    assert to_delete(names, NOW, kept={names[0]}) == []        # unless the other is kept
    assert to_delete(names[:2], NOW) == []                      # the line's newest always stays


def test_each_line_is_thinned_on_its_own():
    names = hourly(48, "001") + [name(NOW - timedelta(days=40), "002")]
    gone = to_delete(names, NOW)
    assert all(n.startswith("001-") for n in gone)              # 002's only point is its newest


def test_odd_names_are_left_alone():
    assert to_delete(["junk", "001-2020-01-01-0000", "001-2020-01-01-0001x"], NOW) == []
