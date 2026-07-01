from typing import Callable

from filters.technical_filter import check_technical_filters

SymbolFilterFn = Callable[[dict], tuple[bool, str]]

SYMBOL_FILTERS: list[SymbolFilterFn] = [
    check_technical_filters,
]


def run_symbol_filters(snapshot: dict) -> tuple[bool, str]:
    for fn in SYMBOL_FILTERS:
        passed, reason = fn(snapshot)
        if not passed:
            return False, reason
    return True, ""
