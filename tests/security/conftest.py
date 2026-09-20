import os

from hypothesis import HealthCheck, settings

_HEALTH = [HealthCheck.too_slow, HealthCheck.data_too_large]
# Deterministic: the same examples every run, so a failure is reproducible from the test id alone.
settings.register_profile(
    "security-fast",
    max_examples=200,
    derandomize=True,
    deadline=None,
    database=None,
    suppress_health_check=_HEALTH,
)
# Randomized and larger; a failure prints @reproduce_failure. Pin a run with --hypothesis-seed=N.
settings.register_profile(
    "security-deep",
    max_examples=3000,
    derandomize=False,
    print_blob=True,
    deadline=None,
    database=None,
    suppress_health_check=_HEALTH,
)
# Used only by mutation runs: mutmut re-runs the suite once per mutant, so keep examples few.
settings.register_profile(
    "security-mutation",
    max_examples=25,
    derandomize=True,
    deadline=None,
    database=None,
    suppress_health_check=_HEALTH,
)
settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "security-fast"))
