"""Queue primitives shared by the GUI and headless agents.

The GUI still owns Qt widgets, but queue mutation is kept here so ordering and
current-track invariants are testable without a QApplication.
"""

from copy import copy
import random
from typing import Any, Dict, Iterable, List, Optional, Sequence


Track = Dict[str, Any]


def _track_key(item: Track) -> str:
    return str(item.get("path") or item.get("id") or item.get("title") or "")


def shuffle_items(items: Sequence[Track], seed: Optional[int] = None) -> List[Track]:
    """Return a deterministic-when-seeded Fisher-Yates shuffle.

    The input list and its track dictionaries are never mutated.
    """

    result = list(items)
    random.Random(seed).shuffle(result)
    return result


class DynamicQueue:
    """Mutable queue with stable current-item tracking.

    ``current_index`` is zero-based for Python callers. ``position`` is the
    one-based value intended for user-facing telemetry.
    """

    def __init__(self, items: Optional[Iterable[Track]] = None, current_index: int = -1):
        self.items: List[Track] = list(items or [])
        self.current_index = current_index if 0 <= current_index < len(self.items) else -1

    @property
    def current(self) -> Optional[Track]:
        if 0 <= self.current_index < len(self.items):
            return self.items[self.current_index]
        return None

    @property
    def position(self) -> int:
        return self.current_index + 1 if self.current is not None else 0

    def append(self, item: Track, play_next: bool = False) -> int:
        if play_next and self.current is not None:
            index = self.current_index + 1
            self.items.insert(index, item)
        else:
            self.items.append(item)
            index = len(self.items) - 1
        if self.current is None and self.items:
            self.current_index = 0
        return index

    def set_current(self, index: int) -> Optional[Track]:
        if not 0 <= index < len(self.items):
            return None
        self.current_index = index
        return self.items[index]

    def remove(self, index: int) -> Optional[Track]:
        if not 0 <= index < len(self.items):
            return None
        removed = self.items.pop(index)
        if not self.items:
            self.current_index = -1
        elif index < self.current_index:
            self.current_index -= 1
        elif index == self.current_index:
            self.current_index = min(index, len(self.items) - 1)
        return removed

    def move(self, source: int, target: int) -> bool:
        """Move one row and preserve the same current track."""

        if not (0 <= source < len(self.items)):
            return False
        target = max(0, min(target, len(self.items) - 1))
        if source == target:
            return True
        item = self.items.pop(source)
        self.items.insert(target, item)
        if self.current_index == source:
            self.current_index = target
        elif source < self.current_index <= target:
            self.current_index -= 1
        elif target <= self.current_index < source:
            self.current_index += 1
        return True

    def reorder(self, order: Sequence[int]) -> bool:
        """Apply a row-index permutation emitted by a drag-and-drop widget."""

        if len(order) != len(self.items) or sorted(order) != list(range(len(self.items))):
            return False
        current_item = self.current
        self.items = [self.items[index] for index in order]
        if current_item is None:
            self.current_index = -1
        else:
            self.current_index = next(
                (i for i, item in enumerate(self.items) if item is current_item), -1
            )
        return True

    def shuffle_remaining(self, seed: Optional[int] = None) -> None:
        """Shuffle tracks after the current track without restarting playback."""

        if self.current is None:
            self.items = shuffle_items(self.items, seed=seed)
            return
        head = self.items[: self.current_index + 1]
        tail = shuffle_items(self.items[self.current_index + 1 :], seed=seed)
        self.items = head + tail

    def clear(self) -> None:
        self.items.clear()
        self.current_index = -1

    def snapshot(self, limit: int = 100) -> List[Track]:
        return [copy(item) for item in self.items[: max(0, limit)]]
