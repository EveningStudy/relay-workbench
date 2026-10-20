"""Shared epoch nanosecond clock."""
from time import time_ns


def now_ns():
    return time_ns()
