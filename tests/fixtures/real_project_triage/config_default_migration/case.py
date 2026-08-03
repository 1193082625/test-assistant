from app.service import PaginationParams


def test_default_page_size():
    actual = PaginationParams.page_size
    assert actual == 10, f"Expected page size 10, got {actual}"
