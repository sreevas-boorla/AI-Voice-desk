import sys
import asyncio
from pathlib import Path

# Add voice-worker directory to sys.path so TurnQueueManager can be imported directly
voice_worker_path = Path(__file__).resolve().parents[2] / "voice-worker"
if str(voice_worker_path) not in sys.path:
    sys.path.insert(0, str(voice_worker_path))

from turn_manager import TurnQueueManager


def test_turn_queue_fifo_and_single_inflight():
    """
    Verifies that TurnQueueManager processes turns in strict FIFO order
    and ensures exactly one turn is in flight at a time.
    """
    async def scenario():
        turn_mgr = TurnQueueManager()
        processed_order = []
        in_flight = 0
        max_concurrent = 0

        async def mock_handler(text: str):
            nonlocal in_flight, max_concurrent
            in_flight += 1
            if in_flight > max_concurrent:
                max_concurrent = in_flight
            # Simulate latency where earlier item takes longer
            await asyncio.sleep(0.04 if text == "First" else 0.01)
            processed_order.append(text)
            in_flight -= 1

        turn_mgr.start_consumer(mock_handler)

        assert turn_mgr.enqueue("First") is True
        assert turn_mgr.enqueue("Second") is True
        assert turn_mgr.enqueue("Third") is True

        await turn_mgr.queue.join()
        await turn_mgr.shutdown()

        assert processed_order == ["First", "Second", "Third"], "Turns must execute in strict FIFO order"
        assert max_concurrent == 1, "Only one turn must be in flight concurrently"

    asyncio.run(scenario())


def test_turn_queue_rapid_transcript_deduplication():
    """
    Verifies that rapid duplicate transcripts within the deduplication window
    are ignored, while new or subsequent identical transcripts are enqueued.
    """
    turn_mgr = TurnQueueManager(deduplication_window_seconds=2.0)

    # 1. First utterance at t=10.0 -> enqueued
    assert turn_mgr.enqueue("Book Dr. Aisha", timestamp=10.0) is True

    # 2. Duplicate within 2s at t=10.8 -> filtered out
    assert turn_mgr.enqueue("Book Dr. Aisha", timestamp=10.8) is False

    # 3. Case-insensitive duplicate at t=11.5 -> filtered out
    assert turn_mgr.enqueue("book dr. aisha", timestamp=11.5) is False

    # 4. Different utterance at t=11.8 -> enqueued
    assert turn_mgr.enqueue("Confirm appointment", timestamp=11.8) is True

    # 5. Same utterance after window at t=14.0 -> enqueued
    assert turn_mgr.enqueue("Confirm appointment", timestamp=14.0) is True

    assert turn_mgr.queue.qsize() == 3


def test_turn_queue_idle_cancellation():
    """
    Verifies that cancelling an idle consumer (waiting on queue.get())
    does not cause 'ValueError: task_done() called too many times'
    and leaves no unhandled exceptions.
    """
    async def scenario():
        turn_mgr = TurnQueueManager()

        async def mock_handler(text: str):
            pass

        task = turn_mgr.start_consumer(mock_handler)
        # Give the loop time to reach queue.get()
        await asyncio.sleep(0.01)

        # Idle consumer shutdown
        await turn_mgr.shutdown()

        assert task.done()
        # Confirm no unhandled task exception occurred (e.g. ValueError)
        try:
            exc = task.exception()
            assert exc is None, f"Expected clean task completion without unhandled exception, got {exc}"
        except asyncio.CancelledError:
            pass

    asyncio.run(scenario())


def test_turn_queue_cancellation_during_processing():
    """
    Verifies that cancelling during active turn processing
    cleans up without task_done accounting errors or orphaned tasks.
    """
    async def scenario():
        turn_mgr = TurnQueueManager()
        processing_started = asyncio.Event()

        async def long_handler(text: str):
            processing_started.set()
            await asyncio.sleep(5.0)

        task = turn_mgr.start_consumer(long_handler)
        turn_mgr.enqueue("Long running task")

        await processing_started.wait()

        # Cancel while mid-flight
        await turn_mgr.shutdown()

        assert task.done()
        try:
            exc = task.exception()
            assert exc is None, f"Expected no unhandled exception, got {exc}"
        except asyncio.CancelledError:
            pass

    asyncio.run(scenario())


def test_turn_queue_failed_turn_followed_by_successful_turn():
    """
    Verifies that a failure during one turn does not crash the consumer loop,
    allowing subsequent turns to be processed normally.
    """
    async def scenario():
        turn_mgr = TurnQueueManager()
        attempts = []

        async def mock_handler(text: str):
            attempts.append(text)
            if text == "Failing turn":
                raise RuntimeError("Simulated API failure")
            await asyncio.sleep(0.01)

        task = turn_mgr.start_consumer(mock_handler)

        turn_mgr.enqueue("Failing turn")
        turn_mgr.enqueue("Succeeding turn")

        await turn_mgr.queue.join()
        await turn_mgr.shutdown()

        assert attempts == ["Failing turn", "Succeeding turn"]
        assert task.done()

    asyncio.run(scenario())


def test_turn_queue_shutdown_no_orphaned_tasks():
    """
    Verifies that repeated start and shutdown cycles leave no running orphaned tasks.
    """
    async def scenario():
        turn_mgr = TurnQueueManager()

        async def mock_handler(text: str):
            await asyncio.sleep(0.01)

        task1 = turn_mgr.start_consumer(mock_handler)
        turn_mgr.enqueue("Sample 1")
        await turn_mgr.queue.join()
        await turn_mgr.shutdown()
        assert task1.done()

        # Restart consumer
        task2 = turn_mgr.start_consumer(mock_handler)
        turn_mgr.enqueue("Sample 2")
        await turn_mgr.queue.join()
        await turn_mgr.shutdown()
        assert task2.done()

    asyncio.run(scenario())
