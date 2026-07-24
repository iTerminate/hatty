# hatty — MIT License. See LICENSE file for details.
"""Min/max-per-bucket decimation for dense plots (issue #68).

A sensor that emits a couple thousand points over a few hours makes plotext do
~12x the rasterization work for a terminal that's only ~200 columns wide, with
zero visual gain. This reduces a series to at most ~2 points per horizontal
bucket *for rendering only* — the caller keeps the raw series for stats, cursor
inspection and saving.

Min/max (not stride or mean) decimation is used deliberately: it always keeps the
extreme sample in each bucket, so spikes in power/CO2-style data survive instead
of being averaged away.
"""


def minmax_downsample(
    times: list[float], values: list[float], buckets: int
) -> tuple[list[float], list[float]]:
    """Reduce parallel (times, values) to at most 2 points per time-bucket.

    Returns the series unchanged when it already fits (``len <= 2*buckets``),
    when ``buckets < 1``, or when the time span is degenerate. Output stays sorted
    by time; within a bucket the min and max are emitted in their original time
    order so line plots don't zig-zag backwards.
    """
    n = len(values)
    if buckets < 1 or n <= 2 * buckets:
        return times, values

    t_first = times[0]
    t_last = times[-1]
    span = t_last - t_first
    if span <= 0:
        return times, values

    out_times: list[float] = []
    out_values: list[float] = []

    # Walk the series once, grouping consecutive points into equal-time buckets.
    bucket_min_i = bucket_max_i = 0
    current_bucket = 0

    def _flush(min_i: int, max_i: int) -> None:
        lo, hi = (min_i, max_i) if min_i <= max_i else (max_i, min_i)
        out_times.append(times[lo])
        out_values.append(values[lo])
        if hi != lo:
            out_times.append(times[hi])
            out_values.append(values[hi])

    for i in range(n):
        b = int((times[i] - t_first) / span * buckets)
        if b >= buckets:
            b = buckets - 1
        if b != current_bucket:
            _flush(bucket_min_i, bucket_max_i)
            current_bucket = b
            bucket_min_i = bucket_max_i = i
        else:
            if values[i] < values[bucket_min_i]:
                bucket_min_i = i
            if values[i] > values[bucket_max_i]:
                bucket_max_i = i

    _flush(bucket_min_i, bucket_max_i)
    return out_times, out_values
