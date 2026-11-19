import pytest

from app.services.geo import parse_geo
from app.services.shares import ShareError, Slot, rebalance


def shares(*specs):
    return [Slot(i, s, p) for i, (s, p) in enumerate(specs)]


def test_even_split_with_remainder_to_first():
    assert rebalance(shares((0, False), (0, False), (0, False))) == {0: 34, 1: 33, 2: 33}


def test_four_offers_25_each():
    assert list(rebalance(shares(*[(0, False)] * 4)).values()) == [25, 25, 25, 25]


def test_pinned_kept_rest_split_like_in_video():
    # 25% закреплено, 75% на двоих → 38/37
    assert rebalance(shares((0, False), (0, False), (25, True))) == {0: 38, 1: 37, 2: 25}


def test_single_offer_gets_100():
    assert rebalance(shares((13, False))) == {0: 100}


def test_pinned_over_100_rejected():
    with pytest.raises(ShareError):
        rebalance(shares((60, True), (50, True), (0, False)))


def test_all_pinned_must_sum_100():
    assert rebalance(shares((40, True), (60, True))) == {0: 40, 1: 60}
    with pytest.raises(ShareError):
        rebalance(shares((40, True), (50, True)))


def test_pinned_100_leaves_zero_for_free():
    assert rebalance(shares((100, True), (0, False), (0, False))) == {0: 100, 1: 0, 2: 0}


def test_sum_always_100():
    for n in range(1, 30):
        for pinned in (0, 7, 33, 99):
            slots = [Slot(0, pinned, True)] + [Slot(i, 0, False) for i in range(1, n + 1)]
            assert sum(rebalance(slots).values()) == 100


def test_geo_parsing():
    assert parse_geo("mx, AU;ro  mx") == ["MX", "AU", "RO"]
    assert parse_geo(["uk"]) == ["GB"]
    with pytest.raises(ValueError):
        parse_geo("XX,AU")
    with pytest.raises(ValueError):
        parse_geo(" , ")
