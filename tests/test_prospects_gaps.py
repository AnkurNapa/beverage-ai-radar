from radar.prospects.gaps import GAP_MIN_COUNT, compute, format_gaps


def _rows(spec):
    """spec: {region: (n_tier12, n_tier45)}"""
    out = []
    for region, (a, b) in spec.items():
        out += [{"region": region, "tier": 1, "vertical": "beer"} for _ in range(a)]
        out += [{"region": region, "tier": 4, "vertical": "beer"} for _ in range(b)]
    return out


def test_thin_region_is_a_gap_and_fat_region_is_not():
    rows = _rows({"India": (24, 23), "Korea": (0, 1)})
    g = compute(rows)
    values = [x["value"] for x in g["regions"]]
    assert "Korea" in values
    assert "India" not in values


def test_both_tests_must_fail_before_a_slice_counts_as_a_gap():
    """A slice with a big count is not a gap even when its share is small."""
    rows = _rows({"A": (0, GAP_MIN_COUNT + 1)}) + _rows({"B": (0, 400)})
    g = compute(rows)
    assert "A" not in [x["value"] for x in g["regions"]]


def test_region_full_of_conferences_still_flags_as_unactionable():
    """20 tier-4 rows is not a region you can sell into."""
    rows = _rows({"Europe": (1, 20)})
    g = compute(rows)
    assert "Europe" not in [x["value"] for x in g["regions"]]
    assert "Europe" in [x["value"] for x in g["actionable"]]


def test_missing_vertical_shows_up_as_a_gap():
    rows = _rows({"India": (30, 0)})  # all beer
    g = compute(rows)
    assert {"whisky", "wine"} <= {x["value"] for x in g["verticals"]}


def test_format_is_readable_and_mentions_totals():
    out = format_gaps(compute(_rows({"Korea": (0, 1)})))
    assert "1 prospects tracked" in out
    assert "Korea" in out
