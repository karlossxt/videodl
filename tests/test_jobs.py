import time

from videodl.jobs import JobStore


def test_new_get_update_delete():
    store = JobStore(session="test")
    job_id = store.new(foo="bar")
    assert store.get(job_id)["foo"] == "bar"
    store.update(job_id, foo="baz")
    assert store.get(job_id)["foo"] == "baz"
    store.delete(job_id)
    assert store.get(job_id) is None


def test_request_cancel():
    store = JobStore(session="test")
    job_id = store.new()
    assert store.request_cancel(job_id) == "cancelling"
    assert store.get(job_id)["cancel"] is True
    store.update(job_id, status="finished")
    assert store.request_cancel(job_id) == "finished"
    assert store.request_cancel("inexistente") is None


def test_cleanup_removes_only_old_terminal_jobs():
    store = JobStore(session="test", ttl_seconds=100)
    finished = store.new(status="finished")
    running = store.new(status="downloading")
    # Envejecemos ambos trabajos por encima del TTL.
    old = time.time() - 500
    store.update(finished, created=old)
    store.update(running, created=old)

    removed = store.cleanup_stale()

    assert removed == 1
    assert store.get(finished) is None
    # El trabajo en curso NO se borra…
    assert store.get(running) is not None
    # …pero se pide su cancelación (hard TTL) para que termine solo.
    assert store.get(running)["cancel"] is True


def test_cleanup_keeps_recent_jobs():
    store = JobStore(session="test", ttl_seconds=3600)
    job_id = store.new(status="finished")
    assert store.cleanup_stale() == 0
    assert store.get(job_id) is not None


def test_active_tmpdirs():
    store = JobStore(session="test")
    running = store.new(status="downloading", tmpdir="/tmp/a")
    finished = store.new(status="finished", tmpdir="/tmp/b")
    active = store.active_tmpdirs()
    assert store.get(running)["tmpdir"] == "/tmp/a"
    assert store.get(finished)["tmpdir"] == "/tmp/b"
    assert "/tmp/a" in active
    assert "/tmp/b" not in active
    assert store.count_active() == 1
