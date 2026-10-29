"""Editable token-price scenarios; no hardcoded model availability or prices."""
from __future__ import annotations
from datetime import date
from pydantic import Field,model_validator
from schemas import Contract,NonNegative,Usage,Evidence

class ModelPrice(Contract):
    model: str=Field(min_length=1)
    input_usd_per_million: NonNegative
    cached_input_usd_per_million: NonNegative
    output_usd_per_million: NonNegative
    evidence: Evidence

class PricingCatalog(Contract):
    last_updated: date
    currency: str=Field(default='USD',pattern='^USD$')
    prices: list[ModelPrice]
    notes: str
    @model_validator(mode='after')
    def unique_models(self):
        if len({p.model for p in self.prices})!=len(self.prices):raise ValueError('Duplicate model price.')
        return self

def price_usage(usage: Usage,catalog: PricingCatalog) -> float | None:
    price=next((p for p in catalog.prices if p.model==usage.model),None)
    if price is None:return None
    return ((usage.input_tokens-usage.cached_input_tokens)*price.input_usd_per_million+
        usage.cached_input_tokens*price.cached_input_usd_per_million+
        usage.output_tokens*price.output_usd_per_million)/1_000_000
