# hatty — MIT License. See LICENSE file for details.
def hvac_action_runs(data: list[dict]) -> list[tuple[str, str, str]]:
    """Collapse per-sample hvac_action history into contiguous (start_ts, end_ts, action) runs."""
    runs: list[tuple[str, str, str]] = []
    if not data:
        return runs

    run_action = data[0].get("hvac_action")
    run_start_ts = data[0]["ts"]
    for entry in data[1:]:
        action = entry.get("hvac_action")
        if action != run_action:
            if run_action in ("heating", "cooling"):
                runs.append((run_start_ts, entry["ts"], run_action))
            run_action = action
            run_start_ts = entry["ts"]
    if run_action in ("heating", "cooling"):
        runs.append((run_start_ts, data[-1]["ts"], run_action))
    return runs
