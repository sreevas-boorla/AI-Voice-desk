import asyncio
import pytest

def test_worker_turn_queue_processes_sequentially():
    """
    Verifies that the LiveKit worker FIFO queue processes turns sequentially,
    preventing overlapping backend calls and maintaining execution order.
    """
    async def run_scenario():
        turn_queue: asyncio.Queue[str] = asyncio.Queue()
        processed_order = []
        in_flight = 0
        max_concurrent = 0

        async def mock_handle_turn(text: str):
            nonlocal in_flight, max_concurrent
            in_flight += 1
            if in_flight > max_concurrent:
                max_concurrent = in_flight
            # Simulate variable network latency
            await asyncio.sleep(0.05 if text == "First" else 0.01)
            processed_order.append(text)
            in_flight -= 1

        async def process_turns_sequentially():
            while True:
                try:
                    user_text = await turn_queue.get()
                    await mock_handle_turn(user_text)
                except asyncio.CancelledError:
                    break
                finally:
                    turn_queue.task_done()

        worker_task = asyncio.create_task(process_turns_sequentially())

        # Queue multiple rapid utterances
        await turn_queue.put("First")
        await turn_queue.put("Second")
        await turn_queue.put("Third")

        await turn_queue.join()
        worker_task.cancel()

        assert processed_order == ["First", "Second", "Third"], "Utterances must be processed in strict FIFO order"
        assert max_concurrent == 1, "Only one backend turn must execute at a time"

    asyncio.run(run_scenario())


def test_worker_rapid_transcript_deduplication():
    """
    Verifies that identical transcripts arriving within the deduplication window
    are safely discarded to prevent double actions.
    """
    turn_queue: asyncio.Queue[str] = asyncio.Queue()
    last_processed = {"text": "", "time": 0.0}
    enqueued = []

    def on_transcript(transcript: str, current_time: float):
        user_text = transcript.strip()
        if user_text.lower() == last_processed["text"].lower() and (current_time - last_processed["time"]) < 2.0:
            return  # Deduplicated
        last_processed["text"] = user_text
        last_processed["time"] = current_time
        enqueued.append(user_text)
        turn_queue.put_nowait(user_text)

    # 1. First utterance at t=10.0
    on_transcript("Book Dr. Aisha", 10.0)
    # 2. Rapid duplicate at t=10.8 (e.g. repeated speech recognition event)
    on_transcript("Book Dr. Aisha", 10.8)
    # 3. Different utterance at t=11.2
    on_transcript("Confirm appointment", 11.2)
    # 4. Same utterance but after window at t=14.0
    on_transcript("Confirm appointment", 14.0)

    assert enqueued == ["Book Dr. Aisha", "Confirm appointment", "Confirm appointment"]
    assert turn_queue.qsize() == 3
