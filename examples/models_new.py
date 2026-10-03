from typing import Literal
from pydantic import BaseModel


class Movie(BaseModel):
    title: str
    year: int
    runtime: int
    rated: Literal["G", "PG", "PG-13", "R"]
