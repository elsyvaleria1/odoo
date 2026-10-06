import pytest

from .conftest import requires_pg


@requires_pg
class TestCommitCountOrdering:
    def test_starts_at_zero_and_counts_each_commit(self, scratch_cursor):
        assert scratch_cursor.commit_count == 0
        scratch_cursor.commit()
        assert scratch_cursor.commit_count == 1
        scratch_cursor.commit()
        assert scratch_cursor.commit_count == 2, "one increment per COMMIT, no skips"

    def test_postcommit_hook_sees_the_count_already_incremented(self, scratch_cursor):
        before = scratch_cursor.commit_count
        seen = {}

        def hook():
            seen["count"] = scratch_cursor.commit_count

        scratch_cursor.postcommit.add(hook)
        scratch_cursor.commit()
        assert seen["count"] == before + 1, (
            "the post-commit hook must observe the bumped count, not the old one"
        )

    def test_a_raising_postcommit_hook_still_reads_as_durable(self, scratch_cursor):
        before = scratch_cursor.commit_count

        def boom():
            raise RuntimeError("post-commit hook blew up")

        scratch_cursor.postcommit.add(boom)
        with pytest.raises(RuntimeError, match="blew up"):
            scratch_cursor.commit()
        assert scratch_cursor.commit_count == before + 1

    def test_a_raising_postcommit_hook_leaves_the_later_ones_to_run(
        self, scratch_cursor
    ):
        ran = []

        def boom():
            raise RuntimeError("post-commit hook blew up")

        scratch_cursor.postcommit.add(lambda: ran.append("first"))
        scratch_cursor.postcommit.add(boom)
        scratch_cursor.postcommit.add_durable(lambda: ran.append("durable"))
        with pytest.raises(RuntimeError, match="blew up"):
            scratch_cursor.commit()
        assert ran == ["first", "durable"], (
            "the transaction is committed: a hook after the failing one gets no "
            "second chance, so it must run now"
        )
        assert len(scratch_cursor.postcommit) == 0
