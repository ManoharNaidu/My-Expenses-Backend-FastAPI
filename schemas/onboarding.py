from pydantic import BaseModel
from typing import Optional, List


class OnboardingRequest(BaseModel):
    categories: List[dict[str, Optional[str]]]

