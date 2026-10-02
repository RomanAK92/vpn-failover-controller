"""Pure priority selection; no networking or file access."""
def select_path(active, healthy, failures, recoveries, failure_threshold, recovery_threshold):
    if active is None or failures[active] >= failure_threshold:
        return next((i for i, up in enumerate(healthy) if up), None)
    if active > 0:
        recovered = next((i for i in range(active) if recoveries[i] >= recovery_threshold), None)
        if recovered is not None:
            return recovered
    return active
