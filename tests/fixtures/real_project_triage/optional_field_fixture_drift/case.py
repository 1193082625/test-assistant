from unittest.mock import MagicMock

from app.model import Fragrance
from app.schema import FragranceResponse


def test_old_fixture_omits_new_optional_fields():
    fragrance = MagicMock(spec=Fragrance)
    FragranceResponse.model_validate(
        {
            "purchase_url": fragrance.purchase_url,
            "purchase_platform": fragrance.purchase_platform,
            "purchase_price": fragrance.purchase_price,
            "purchase_currency": fragrance.purchase_currency,
        }
    )
