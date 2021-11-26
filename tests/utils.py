from typing import List, Dict, Union, Any


def assert_json_equal(actual: Any, expected: Any):
    ignored_paths = _get_ignored_paths(expected, [])
    if ignored_paths is not None:
        _ignore_paths(actual, ignored_paths)

    assert actual == expected


def _get_ignored_paths(expected: Union[Dict, List], parent_path: List[Union[str, int]]) -> List[List[Any]]:
    paths = []
    if isinstance(expected, list):
        for i, value in enumerate(expected):
            ignored = _get_ignored_paths(value, parent_path + [i])
            if ignored is not None:
                paths.extend(ignored)
    elif isinstance(expected, dict):
        for key, value in expected.items():
            ignored = _get_ignored_paths(value, parent_path + [key])
            if ignored is not None:
                paths.extend(ignored)
    elif isinstance(expected, type(...)):
        return [parent_path]

    return paths if not len(paths) == 0 else None


def _ignore_paths(actual: dict, paths: List[List[Union[str, int]]]):
    for path in paths:
        current = actual
        for step in path[:-1]:
            current = current[step]
        current[path[-1]] = ...

