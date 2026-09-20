"""Fixture module docstring."""

import math

THRESHOLD = 10.0


def first_function(value):
    """First."""
    return value * 2


@staticmethod
def decorated_function(value):
    """Decorated: the chunk must start at the decorator, not the def."""
    return value + 1


class SmallClass:
    """A short class stays whole."""

    def method_a(self):
        return 1

    def method_b(self):
        return 2


def last_function():
    """Last."""
    return math.pi
