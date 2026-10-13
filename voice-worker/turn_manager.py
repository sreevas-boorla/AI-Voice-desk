"""
TurnQueueManager Component
Provides FIFO sequential turn processing, rapid transcript deduplication,
and safe cancellation/shutdown without orphaned tasks or ValueError on task_done().
"""

import asyncio
import time
import logging
from typing import Callable, Awaitable, Optional

logger = logging.getLogger("voicedesk-worker.turn-manager")

class TurnQueueManager:
    def __init__(self, deduplication_window_seconds: float = 2.0):
        self.queue: asyncio.Queue[str] = asyncio.Queue()
        self.deduplication_window_seconds = deduplication_window_seconds
        self.last_text: str = ""
        self.last_time: float = 0.0
        self._consumer_task: Optional[asyncio.Task] = None
        self._is_running = False

    def enqueue(self, transcript: str, timestamp: Optional[float] = None) -> bool:
        """
        Enqueues a transcript for sequential processing if it is non-empty
        and not a duplicate within the deduplication window.
        Returns True if enqueued, False if ignored or duplicate.
        """
        text = transcript.strip()
        if not text:
            return False

        now = timestamp if timestamp is not None else time.time()
        if text.lower() == self.last_text.lower() and (now - self.last_time) < self.deduplication_window_seconds:
            return False

        self.last_text = text
        self.last_time = now
        self.queue.put_nowait(text)
        return True

    def start_consumer(self, turn_handler: Callable[[str], Awaitable[None]]) -> asyncio.Task:
        """
        Starts the sequential consumer task.
        Guarantees that task_done() is only called after an item was successfully dequeued.
        """
        if self._consumer_task and not self._consumer_task.done():
            return self._consumer_task

        self._is_running = True

        async def _consumer_loop():
            while self._is_running:
                try:
                    # Wait for next turn
                    user_text = await self.queue.get()
                except asyncio.CancelledError:
                    # Interrupted while waiting on queue.get(); do NOT call task_done()
                    break

                # An item was successfully dequeued; must call task_done() exactly once
                try:
                    await turn_handler(user_text)
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"Error handling turn: {type(e).__name__}")
                finally:
                    self.queue.task_done()

        self._consumer_task = asyncio.create_task(_consumer_loop())
        return self._consumer_task

    async def shutdown(self):
        """
        Gracefully cancels the consumer task and awaits its completion,
        ensuring no orphaned tasks or unhandled task exceptions remain.
        """
        self._is_running = False
        if self._consumer_task and not self._consumer_task.done():
            self._consumer_task.cancel()
            try:
                await self._consumer_task
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.error(f"Error during consumer task shutdown: {type(e).__name__}")
            finally:
                self._consumer_task = None
