# hatty — MIT License. See LICENSE file for details.
"""Unit tests for min/max-per-bucket downsampling (issue #68)."""

from hatty.ui.graph.downsample import minmax_downsample


def test_passes_through_when_already_small():
    times = [0.0, 1.0, 2.0, 3.0]
    values = [10.0, 11.0, 12.0, 13.0]
    # 4 points, 4 buckets -> 4 <= 2*4, unchanged (same objects).
    out_t, out_v = minmax_downsample(times, values, buckets=4)
    assert out_t is times
    assert out_v is values


def test_passes_through_for_nonpositive_buckets():
    times = [float(i) for i in range(100)]
    values = [float(i) for i in range(100)]
    assert minmax_downsample(times, values, buckets=0) == (times, values)


def test_reduces_dense_series_to_about_two_per_bucket():
    n = 2000
    times = [float(i) for i in range(n)]
    values = [float(i % 7) for i in range(n)]
    out_t, out_v = minmax_downsample(times, values, buckets=100)
    assert len(out_v) <= 2 * 100
    assert len(out_v) < n


def test_output_is_time_sorted():
    n = 1000
    times = [float(i) for i in range(n)]
    values = [float((i * 37) % 101) for i in range(n)]
    out_t, _ = minmax_downsample(times, values, buckets=50)
    assert out_t == sorted(out_t)


def test_spike_is_preserved():
    # A single tall spike buried in a flat series must survive decimation.
    n = 1000
    times = [float(i) for i in range(n)]
    values = [0.0] * n
    values[512] = 999.0
    out_t, out_v = minmax_downsample(times, values, buckets=20)
    assert 999.0 in out_v
    # And the min (0.0) is kept too.
    assert 0.0 in out_v


def test_trough_is_preserved():
    n = 1000
    times = [float(i) for i in range(n)]
    values = [5.0] * n
    values[100] = -50.0
    out_t, out_v = minmax_downsample(times, values, buckets=10)
    assert -50.0 in out_v


def test_within_bucket_min_max_emitted_in_time_order():
    # One bucket, min occurs before max -> min emitted first.
    times = [0.0, 1.0, 2.0, 3.0, 4.0, 5.0]
    values = [1.0, -1.0, 0.5, 0.5, 9.0, 2.0]  # min at idx1 (t=1), max at idx4 (t=4)
    out_t, out_v = minmax_downsample(times, values, buckets=1)
    assert out_t == [1.0, 4.0]
    assert out_v == [-1.0, 9.0]


def test_empty_and_single_point():
    assert minmax_downsample([], [], buckets=10) == ([], [])
    assert minmax_downsample([5.0], [1.0], buckets=10) == ([5.0], [1.0])


def test_degenerate_time_span_passes_through():
    times = [3.0, 3.0, 3.0, 3.0, 3.0, 3.0]
    values = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]
    assert minmax_downsample(times, values, buckets=1) == (times, values)
