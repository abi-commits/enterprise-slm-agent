"""Pydantic schemas for the Query Optimizer."""

from typing import Optional

from pydantic import BaseModel, Field


class OptimizeRequest(BaseModel):
    """Request schema for query optimization."""

    query: str = Field(
        ...,
        min_length=1,
        max_length=1000,
        description="The raw user query to optimize",
        examples=["What is the vacation policy?"],
    )
    user_context: Optional[str] = Field(
        default=None,
        description="Additional user context (role, department, etc.)",
        examples=["User is in HR department"],
    )


class OptimizeResponse(BaseModel):
    """Response schema for query optimization."""

    optimized_queries: list[str] = Field(
        ...,
        description="List of optimized queries for better retrieval",
        examples=[
            [
                "company vacation policy guidelines 2024",
                "employee paid time off PTO policy",
                "vacation leave entitlements and accrual rules",
            ]
        ],
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Confidence score (0.0 to 1.0) for query clarity",
        examples=[0.85],
    )
    keywords: list[str] = Field(
        ...,
        description="Extracted keywords from the query",
        examples=[["vacation", "PTO", "paid time off", "leave", "policy"]],
    )
    processing_time_ms: float = Field(
        ...,
        description="Time taken to process the query in milliseconds",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "optimized_queries": [
                        "company vacation policy guidelines 2024",
                        "employee paid time off PTO policy",
                        "vacation leave entitlements and accrual rules",
                    ],
                    "confidence": 0.85,
                    "keywords": [
                        "vacation",
                        "PTO",
                        "paid time off",
                        "leave",
                        "policy",
                        "employee benefits",
                    ],
                    "processing_time_ms": 125.5,
                }
            ]
        }
    }
