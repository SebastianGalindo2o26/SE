"""Política de negocio para detectar fallas consecutivas de una misma API."""

from typing import Iterable, Protocol


class Observation(Protocol):
    target_url: str | None
    status_code: int | None
    expected_status: int
    error_type: str | None


def count_consecutive_failures(observations: Iterable[Observation], target_url: str) -> int:
    count = 0
    for item in observations:
        failed = item.target_url == target_url and (
            item.error_type == "timeout"
            or (
                item.status_code is not None
                and 500 <= item.status_code < 600
                and item.status_code != item.expected_status
            )
        )
        if not failed:
            break
        count += 1
    return count
