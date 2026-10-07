from contextlib import nullcontext
from unittest.mock import patch


def flush_after_commit(env) -> None:
    """Run what the transaction left for after its commit -- the credential
    counters among it -- inside the test's own transaction, which never
    commits, and read the records afresh. A commit flushes before it runs
    them, so this does too: a write still pending would land on top."""
    env.flush_all()
    with patch.object(env.registry, "cursor", lambda: nullcontext(env.cr)):
        env.cr.postcommit.run()
    env.invalidate_all()
