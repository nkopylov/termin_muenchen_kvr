# ABOUTME: Tests for the shared captcha token cache: reuse, refresh before expiry, single solve.
# ABOUTME: The solver and the clock are replaced; no network is touched.

import asyncio

import pytest

from src.services import captcha_token
from src.services.locks import keyed_lock


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


@pytest.fixture
def clock(monkeypatch):
    c = Clock()
    monkeypatch.setattr(captcha_token, "_clock", c)
    return c


@pytest.fixture
def solver(monkeypatch):
    state = {"calls": 0, "result": "tok", "gate": None}

    async def solve():
        state["calls"] += 1
        if state["gate"] is not None:
            await state["gate"].wait()
        result = state["result"]
        return f"{result}{state['calls']}" if result else result

    monkeypatch.setattr(captcha_token, "_solve", solve)
    captcha_token.invalidate()
    yield state
    captcha_token.invalidate()


@pytest.mark.asyncio
class TestGetToken:
    async def test_solves_once_and_reuses(self, clock, solver):
        assert await captcha_token.get_token() == "tok1"
        clock.now += 200
        assert await captcha_token.get_token() == "tok1"
        assert solver["calls"] == 1

    async def test_refreshes_when_less_than_min_ttl_left(self, clock, solver):
        await captcha_token.get_token()
        clock.now += 251  # 29 s of the 280 s lifetime left
        assert await captcha_token.get_token(min_ttl=30) == "tok2"

    async def test_token_near_expiry_mid_cycle_is_resolved_before_next_call(
        self, clock, solver
    ):
        assert await captcha_token.get_token(min_ttl=30) == "tok1"
        clock.now += 240
        assert await captcha_token.get_token(min_ttl=30) == "tok1"
        clock.now += 15  # 25 s left: not enough for the next call
        assert await captcha_token.get_token(min_ttl=30) == "tok2"
        clock.now += 10
        assert await captcha_token.get_token(min_ttl=60) == "tok2"

    async def test_expired_token_is_resolved(self, clock, solver):
        await captcha_token.get_token()
        clock.now += 281
        assert await captcha_token.get_token(min_ttl=0) == "tok2"

    async def test_single_solve_under_concurrent_calls(self, clock, solver):
        solver["gate"] = asyncio.Event()
        tasks = [asyncio.create_task(captcha_token.get_token()) for _ in range(5)]
        await asyncio.sleep(0)
        solver["gate"].set()
        assert await asyncio.gather(*tasks) == ["tok1"] * 5
        assert solver["calls"] == 1

    async def test_failure_returns_none_and_is_not_cached(self, clock, solver):
        solver["result"] = None
        assert await captcha_token.get_token() is None
        solver["result"] = "ok"
        assert await captcha_token.get_token() == "ok2"

    async def test_solver_exception_returns_none(self, clock, monkeypatch):
        async def boom():
            raise ConnectionError("network down")

        monkeypatch.setattr(captcha_token, "_solve", boom)
        captcha_token.invalidate()
        assert await captcha_token.get_token() is None

    async def test_invalidate_forces_new_token(self, clock, solver):
        await captcha_token.get_token()
        captcha_token.invalidate()
        assert await captcha_token.get_token() == "tok2"


class TestIsTokenError:
    @pytest.mark.parametrize(
        "code", ["captchaInvalid", "captchaExpired", "captchaMissing"]
    )
    def test_token_codes(self, code):
        assert captcha_token.is_token_error(("other", code)) is True

    def test_other_codes(self):
        assert (
            captcha_token.is_token_error(("invalidLocationAndServiceCombination",))
            is False
        )
        assert captcha_token.is_token_error(()) is False


@pytest.mark.asyncio
class TestKeyedLock:
    async def test_same_key_same_lock_within_a_loop(self):
        assert keyed_lock("t", 1) is keyed_lock("t", 1)
        assert keyed_lock("t", 1) is not keyed_lock("t", 2)
        assert keyed_lock("t", 1) is not keyed_lock("u", 1)

    async def test_locks_serialize(self):
        order = []

        async def worker(name):
            async with keyed_lock("t", "k"):
                order.append(f"{name}-in")
                await asyncio.sleep(0)
                order.append(f"{name}-out")

        await asyncio.gather(worker("a"), worker("b"))
        assert order == ["a-in", "a-out", "b-in", "b-out"]
