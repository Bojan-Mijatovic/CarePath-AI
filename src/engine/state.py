"""State engine: moves pathway_state forward one simulated day (SPEC §5.1, §9 tick step 2).

Phase 0 stub. Step 1.22 fills it in: update patients with new events on `day`, then sweep
deadlines for everyone.
"""

import duckdb


def update(con: duckdb.DuckDBPyConnection, day: int) -> None:
    """Bring pathway_state up to `day`. Does nothing until step 1.22."""
