from pydantic import BaseModel


class FragranceResponse(BaseModel):
    purchase_url: str | None = None
    purchase_platform: str | None = None
    purchase_price: float | None = None
    purchase_currency: str | None = None
