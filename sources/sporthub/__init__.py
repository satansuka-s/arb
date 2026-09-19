from .adapter import SporthubAdapter


def build_adapter():
    return SporthubAdapter()


__all__ = ["SporthubAdapter", "build_adapter"]
