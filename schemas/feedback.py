from pydantic import BaseModel, Field


class FeedbackCreateRequest(BaseModel):
    description: str = Field(..., min_length=1, max_length=1000)
