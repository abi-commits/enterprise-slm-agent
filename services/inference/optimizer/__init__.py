"""Query Optimizer module for the Inference Service.

Re-exports key classes and functions for backward compatibility.
"""

from services.inference.optimizer.model import QueryOptimizerModel, get_model

__all__ = [
    "QueryOptimizerModel",
    "get_model",
]
