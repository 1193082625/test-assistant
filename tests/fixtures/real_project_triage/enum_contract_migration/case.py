import pytest

from app.schema import OutfitComposeRequest


@pytest.mark.parametrize("layout", ["vertical", "grid"])
def test_legacy_layouts_are_valid(layout):
    OutfitComposeRequest(layout=layout)
