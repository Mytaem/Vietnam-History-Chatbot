import pytest


def pytest_collection_modifyitems(items):
    """Test đánh dấu todo được skip cho tới khi module tương ứng được triển khai."""
    for item in items:
        if "todo" in item.keywords:
            item.add_marker(pytest.mark.skip(reason="chưa triển khai"))
