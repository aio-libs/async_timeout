import asyncio
import os
import time

import pytest

from async_timeout import timeout, timeout_at


@pytest.mark.asyncio
async def test_timeout():
    canceled_raised = False

    async def long_running_task():
        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            nonlocal canceled_raised
            canceled_raised = True
            raise

    with pytest.raises(asyncio.TimeoutError):
        with timeout(0.01) as t:
            await long_running_task()
            assert t._loop is asyncio.get_event_loop()
    assert canceled_raised, 'CancelledError was not raised'


@pytest.mark.asyncio
async def test_timeout_finish_in_time():
    async def long_running_task():
        await asyncio.sleep(0.01)
        return 'done'

    with timeout(0.1):
        resp = await long_running_task()
    assert resp == 'done'


@pytest.mark.asyncio
async def test_timeout_disable():
    async def long_running_task():
        await asyncio.sleep(0.1)
        return 'done'

    loop = asyncio.get_event_loop()
    t0 = loop.time()
    with timeout(None):
        resp = await long_running_task()
    assert resp == 'done'
    dt = loop.time() - t0
    assert 0.09 < dt < 0.13, dt


@pytest.mark.asyncio
async def test_timeout_is_none_no_task():
    with timeout(None) as cm:
        assert cm._timeout_handler is None


@pytest.mark.asyncio
async def test_timeout_enable_zero():
    with pytest.raises(asyncio.TimeoutError):
        with timeout(0) as cm:
            await asyncio.sleep(0.1)

    assert cm.expired


@pytest.mark.asyncio
async def test_timeout_enable_zero_coro_not_started():
    coro_started = False

    async def coro():
        nonlocal coro_started
        coro_started = True

    with pytest.raises(asyncio.TimeoutError):
        with timeout(0) as cm:
            await asyncio.sleep(0.01)
            await coro()

    assert cm.expired
    assert coro_started is False


@pytest.mark.asyncio
async def test_timeout_not_relevant_exception():
    await asyncio.sleep(0)
    with pytest.raises(KeyError):
        with timeout(0.1):
            raise KeyError


@pytest.mark.asyncio
async def test_timeout_canceled_error_is_not_converted_to_timeout():
    await asyncio.sleep(0)
    with pytest.raises(asyncio.CancelledError):
        with timeout(0.001):
            raise asyncio.CancelledError


@pytest.mark.asyncio
async def test_timeout_blocking_loop():
    async def long_running_task():
        time.sleep(0.1)
        return 'done'

    with timeout(0.01):
        result = await long_running_task()
    assert result == 'done'


@pytest.mark.asyncio
async def test_for_race_conditions():
    loop = asyncio.get_event_loop()
    fut = loop.create_future()
    loop.call_later(0.1, fut.set_result('done'))
    with timeout(0.2):
        resp = await fut
    assert resp == 'done'


@pytest.mark.asyncio
async def test_timeout_time():
    foo_running = None
    loop = asyncio.get_event_loop()
    start = loop.time()
    with pytest.raises(asyncio.TimeoutError):
        with timeout(0.1):
            foo_running = True
            try:
                await asyncio.sleep(0.2)
            finally:
                foo_running = False

    dt = loop.time() - start
    if not (0.09 < dt < 0.11) and os.environ.get('APPVEYOR'):
        pytest.xfail('appveyor sometimes is toooo sloooow')
    assert 0.09 < dt < 0.11
    assert not foo_running


def test_raise_runtimeerror_if_no_task():
    with pytest.raises(RuntimeError):
        with timeout(0.1):
            pass


@pytest.mark.asyncio
async def test_outer_coro_is_not_cancelled():

    has_timeout = False

    async def outer():
        nonlocal has_timeout
        try:
            with timeout(0.001):
                await asyncio.sleep(1)
        except asyncio.TimeoutError:
            has_timeout = True

    task = asyncio.ensure_future(outer())
    await task
    assert has_timeout
    assert not task.cancelled()
    assert task.done()


@pytest.mark.asyncio
async def test_cancel_outer_coro():
    loop = asyncio.get_event_loop()
    fut = loop.create_future()

    async def outer():
        fut.set_result(None)
        await asyncio.sleep(1)

    task = asyncio.ensure_future(outer())
    await fut
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert task.cancelled()
    assert task.done()


@pytest.mark.asyncio
async def test_timeout_suppress_exception_chain():
    with pytest.raises(asyncio.TimeoutError) as ctx:
        with timeout(0.01):
            await asyncio.sleep(10)
    assert not ctx.value.__suppress_context__


@pytest.mark.asyncio
async def test_timeout_expired():
    with pytest.raises(asyncio.TimeoutError):
        with timeout(0.01) as cm:
            await asyncio.sleep(10)
    assert cm.expired


@pytest.mark.asyncio
async def test_timeout_inner_timeout_error():
    with pytest.raises(asyncio.TimeoutError):
        with timeout(0.01) as cm:
            raise asyncio.TimeoutError
    assert not cm.expired


@pytest.mark.asyncio
async def test_timeout_inner_other_error():
    with pytest.raises(RuntimeError):
        with timeout(0.01) as cm:
            raise RuntimeError
    assert not cm.expired


@pytest.mark.asyncio
async def test_timeout_at():
    loop = asyncio.get_event_loop()
    with pytest.raises(asyncio.TimeoutError):
        now = loop.time()
        async with timeout_at(now + 0.01) as cm:
            await asyncio.sleep(10)
    assert cm.expired


@pytest.mark.asyncio
async def test_timeout_at_not_fired():
    loop = asyncio.get_event_loop()
    now = loop.time()
    async with timeout_at(now + 1) as cm:
        await asyncio.sleep(0)
    assert not cm.expired


@pytest.mark.asyncio
async def test_expired_after_rejecting():
    t = timeout(10)
    assert not t.expired
    t.reject()
    assert not t.expired


@pytest.mark.asyncio
async def test_expired_after_timeout():
    with pytest.raises(asyncio.TimeoutError):
        async with timeout(0) as t:
            assert not t.expired
            await asyncio.sleep(10)
    assert t.expired
