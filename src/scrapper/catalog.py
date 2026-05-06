"""Płaska iteracja po drzewie serviceVariantsGroups."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass


@dataclass(frozen=True)
class ServiceMatch:
    service_id: int
    name: str
    path: list[str]


def _walk(groups: list[dict], path: list[str]) -> Iterator[ServiceMatch]:
    for node in groups:
        node_id = node.get("id")
        node_name = node.get("name", "")
        children = node.get("children") or []
        new_path = [*path, node_name]
        if not children:
            if node_id is not None:
                yield ServiceMatch(service_id=node_id, name=node_name, path=new_path)
        else:
            yield from _walk(children, new_path)


def find_service_by_id(groups: list[dict], service_id: int) -> ServiceMatch | None:
    for match in _walk(groups, []):
        if match.service_id == service_id:
            return match
    return None


def find_services_by_name(groups: list[dict], query: str) -> list[ServiceMatch]:
    if not query:
        return []
    needle = query.casefold()
    return [m for m in _walk(groups, []) if needle in m.name.casefold()]
