"""Opt-in native Lesson 46 cancellation after an observed first upstream receipt."""

import argparse
import asyncio
import json

import httpx

import agent_lab.cache_lab as cache_lab


async def run() -> dict:
    observed: list[cache_lab.CacheObserver] = []
    original = cache_lab.CacheObserver

    class TrackingObserver(original):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            observed.append(self)

    cache_lab.CacheObserver = TrackingObserver
    task = asyncio.create_task(cache_lab.live_action("anatomy"))
    try:
        async with asyncio.timeout(80):
            while not observed or not observed[0].receipts:
                if task.done():
                    raise ValueError("Native action finished before a cancel point")
                await asyncio.sleep(0.02)
        observer = observed[0]
        receipt_count = len(observer.receipts)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        else:
            raise ValueError("Native action ignored cancellation")
        async with httpx.AsyncClient(timeout=0.5, trust_env=False) as client:
            try:
                await client.post(f"http://127.0.0.1:{observer.port}/v1/messages", json={})
            except (httpx.ConnectError, httpx.ConnectTimeout):
                closed = True
            else:
                closed = False
        if not closed:
            raise ValueError("Owned observer remained reachable after cancellation")
        return {"operation": observer.operation, "receipts_before_cancel": receipt_count,
                "cancelled": True, "listener_closed": True}
    finally:
        cache_lab.CacheObserver = original
        if not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", required=True)
    parser.add_argument("--budget", type=float, required=True)
    args = parser.parse_args()
    if not args.live or args.budget != 0.15:
        parser.error("Confirm --live and the fixed $0.15 session ceiling.")
    print(json.dumps(asyncio.run(run())))


if __name__ == "__main__":
    main()
