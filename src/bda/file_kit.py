from pathlib import Path
from importlib.resources.abc import Traversable


def find_aider_results(path_or_traversable: Path | Traversable):
    return find_files(path_or_traversable, '.aider.results.json')


def find_files(path_or_traversable: Path | Traversable, file_pattern: str) -> list:
    if isinstance(path_or_traversable, Path):
        return sorted(path_or_traversable.rglob(file_pattern))

    # For Traversable implementation
    def _recursive_search(traversable: Traversable) -> Iterator[Traversable]:
        if traversable.is_file() and traversable.name == file_pattern:
            yield traversable
        elif traversable.is_dir():
            for child in traversable.iterdir():
                yield from _recursive_search(child)

    return sorted(_recursive_search(path_or_traversable), key=lambda x: str(x))
