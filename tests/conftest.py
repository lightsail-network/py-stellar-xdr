import os

from hypothesis import HealthCheck, settings

# Every type gets its own test, so each runs few examples by default. Set
# HYPOTHESIS_PROFILE=thorough for a longer run.
#
# There is no deadline, and the health checks about slow or discarded generation are
# off: a large random value, such as a whole ledger, can take long to build under
# coverage, and Hypothesis discards many oversized attempts at the deeply recursive
# types. Neither says anything about the code under test.
for name, examples in [("default", 25), ("thorough", 1000)]:
    settings.register_profile(
        name,
        max_examples=examples,
        deadline=None,
        suppress_health_check=[
            HealthCheck.too_slow,
            HealthCheck.filter_too_much,
            HealthCheck.data_too_large,
        ],
    )
settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "default"))
