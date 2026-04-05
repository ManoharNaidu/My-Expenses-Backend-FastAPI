from typing import Optional

from pydantic import BaseModel, Field


class ReviewStagingRequest(BaseModel):
    staging_ids: Optional[list[str]] = Field(default=None, max_length=100)

