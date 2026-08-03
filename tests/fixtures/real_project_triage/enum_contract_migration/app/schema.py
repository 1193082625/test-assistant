from typing import Annotated

from pydantic import BaseModel, Field


class OutfitComposeRequest(BaseModel):
    layout: Annotated[str, Field(pattern="^(auto|left-right)$")]
