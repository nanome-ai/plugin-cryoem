import asyncio
import functools
import inspect


def run_function_or_coroutine(callback_fn, *args, **kwargs):
    """Run callback function if it is a coroutine or a function."""
    is_async_fn = inspect.iscoroutinefunction(callback_fn)
    is_async_partial = isinstance(callback_fn, functools.partial) and \
        inspect.iscoroutinefunction(callback_fn.func)

    if is_async_fn or is_async_partial:
        task = asyncio.create_task(callback_fn(*args, **kwargs))
        return task
    elif callback_fn:
        callback_fn(*args, **kwargs)
