from typing import Optional
from pydantic import BaseModel


class Movie(BaseModel):
    title: str
    year: int
    runtime: Optional[int] = None
