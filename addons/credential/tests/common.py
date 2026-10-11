from contextlib import nullcontext
from unittest.mock import patch


def flush_after_commit(env) -> None:
    env.flush_all()
    with patch.object(env.registry, "cursor", lambda: nullcontext(env.cr)):
        env.cr.postcommit.run()
    env.invalidate_all()
