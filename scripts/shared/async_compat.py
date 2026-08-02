"""
Async compatibility utilities.

Use _run_async() ONLY in CLI scripts that are not part of an async pipeline.
Never call this from within an async function — use `await` instead.
"""

import asyncio


def run_async(coro):
    """Run async coroutine in sync context. For CLI scripts only.

    IMPORTANT: Do not use inside async pipelines — pool will be left stale.
    """
    try:
        asyncio.get_running_loop()
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor() as pool:
            future = pool.submit(asyncio.run, coro)
            return future.result()
    except RuntimeError:
        return asyncio.run(coro)
