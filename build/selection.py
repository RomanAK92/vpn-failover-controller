"""Pure priority selection; no networking or file access."""
def select_path(active, healthy, failures, recoveries, failure_threshold, recovery_threshold):
    if active is None or failures[active] >= failure_threshold:
        return next((i for i, up in enumerate(healthy) if up), None)
    if active > 0:
        recovered = next((i for i in range(active) if recoveries[i] >= recovery_threshold), None)
        if recovered is not None:
            return recovered
    return active


def select_controlled(active, healthy, failures, recoveries, failure_threshold, recovery_threshold, names, policy=None):
    if policy is None:
        return select_path(active, healthy, failures, recoveries, failure_threshold, recovery_threshold)
    enabled = [i for i, name in enumerate(names) if name not in policy['disabled']]
    if policy['preferred'] is not None:
        preferred = names.index(policy['preferred'])
        enabled.remove(preferred); enabled.insert(0, preferred)
    index = enabled.index(active) if active in enabled else None
    result = select_path(index, [healthy[i] for i in enabled], [failures[i] for i in enabled],
                         [recoveries[i] for i in enabled], failure_threshold, recovery_threshold)
    return enabled[result] if result is not None else None
