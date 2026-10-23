"""Socket-free test loop for the restricted Windows execution host only.

Production uses the normal Uvicorn event loop. This harness runs coroutines,
timers and cancellation, and deliberately rejects any I/O registration.
"""
import asyncio
import os
import selectors
import time


class MemorySelector(selectors.SelectSelector):
    def select(self, timeout=None):
        if self.get_map():
            raise RuntimeError("The unit-test loop cannot perform I/O")
        if timeout:
            time.sleep(timeout)
        return []


class MemoryLoop(asyncio.SelectorEventLoop):
    def __init__(self):
        super().__init__(selector=MemorySelector())

    def _make_self_pipe(self):
        self._ssock = self._csock = None

    def _close_self_pipe(self):
        pass


def run(coroutine):
    if os.environ.get("SHORTFORM_TEST_MEMORY_LOOP") == "1":
        with asyncio.Runner(loop_factory=MemoryLoop) as runner:
            return runner.run(coroutine)
    return asyncio.run(coroutine)
