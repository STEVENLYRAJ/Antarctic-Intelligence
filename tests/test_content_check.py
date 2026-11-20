"""Content check of downloaded raw fields (added after three all-zero NCEP files passed the day-count check).
SYNTHETIC arrays only (software test)."""
import numpy as np
import pytest

from aethentra.data.acquisition import ContentError, content_check

RNG = np.random.default_rng(0)


def test_real_looking_field_passes():
    a = 70 + 10 * RNG.standard_normal((365, 23, 144))
    assert content_check(np.clip(a, 0, 100), "rhum")["status"] == "passed"


@pytest.mark.parametrize("arr", [np.zeros((365, 23, 144)), np.full((365, 23, 144), np.nan), np.full((365, 23, 144), 5.0)])
def test_zero_nan_and_constant_fields_are_rejected(arr):
    with pytest.raises(ContentError):
        content_check(arr, "rhum")


def test_out_of_range_and_flat_days_are_rejected():
    a = 280 + RNG.standard_normal((365, 23, 144))
    bad = a.copy(); bad[10, 0, 0] = 400.0
    with pytest.raises(ContentError):
        content_check(bad, "air")
    flat = a.copy(); flat[:20] = 280.0                      # 20 spatially constant days (> 1 %)
    with pytest.raises(ContentError):
        content_check(flat, "air")


def test_nan_tail_days_allowed():                            # e.g. a current-year file padded with missing days
    a = 280 + RNG.standard_normal((365, 23, 144)); a[76:] = np.nan
    assert content_check(a, "air")["days_with_data"] == 76
