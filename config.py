"""Configuration, public evidence files and runtime-only credentials.

No import-time filesystem mutation or global API client. UI code supplies
Streamlit secrets explicitly, avoiding a Streamlit dependency in this module.
"""
from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel, Field, SecretStr
from schemas import Contract, Stage

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / 'data'
APP_NAME = '🏗️ GharBuilder AI'
DISCLAIMER = ('Preliminary concepts and indicative estimates only. Final designs require '
              'authority approval and review/stamping by a PCATP-registered architect '
              'and PEC-registered structural engineer.')
RAINBOW = ('#E53935', '#FB8C00', '#FDD835', '#43A047', '#1E88E5', '#3949AB', '#8E24AA')

# Edges point from an upstream output to the outputs it invalidates.
DEPENDENCIES: dict[Stage, tuple[Stage, ...]] = {
    Stage.REQUIREMENTS: (Stage.COMPLIANCE,),
    Stage.COMPLIANCE: (Stage.PLANNING,),
    Stage.PLANNING: (Stage.CAD, Stage.STRUCTURAL, Stage.MEP),
    Stage.CAD: (Stage.MODEL,),
    Stage.MODEL: (Stage.BIM,),
    Stage.STRUCTURAL: (Stage.BIM, Stage.SCHEDULE, Stage.COST),
    Stage.MEP: (Stage.BIM, Stage.COST),
    Stage.BIM: (Stage.SCHEDULE, Stage.COST, Stage.TWIN),
    Stage.SCHEDULE: (Stage.LABOUR, Stage.TWIN, Stage.REPORT),
    Stage.COST: (Stage.LABOUR, Stage.TWIN, Stage.REPORT),
    Stage.LABOUR: (Stage.TWIN, Stage.REPORT),
    Stage.TWIN: (Stage.REPORT,),
    Stage.REPORT: (),
}


class ConfigurationError(ValueError):
    """A user-actionable configuration problem, without secret values."""


class Settings(Contract):
    model: str = Field(min_length=1, max_length=150)
    language: str = Field(default='English', pattern=r'^(English|Urdu)$')
    theme: str = Field(default='light', pattern=r'^(light|dark)$')
    max_tool_calls: int = Field(default=30, ge=1, le=100)
    max_output_tokens: int = Field(default=6000, ge=256, le=32000)
    max_retries: int = Field(default=2, ge=0, le=5)
    timeout_seconds: float = Field(default=60, gt=0, le=180)
    contingency_percent: float = Field(default=10, ge=0, le=50)
    allow_settings_writes: bool = False


class Credentials(Contract):
    """Ephemeral only. Excluded from model_dump/model_dump_json, even accidentally."""
    api_key: SecretStr = Field(exclude=True, repr=False)


def resolve_credentials(sidebar_key: str | None = None,
                        secrets: Mapping[str, Any] | None = None) -> Credentials | None:
    """Priority: entered key, injected Streamlit secret, environment. Never persist."""
    raw = (sidebar_key or '').strip()
    if not raw and secrets is not None:
        raw = str(secrets.get('OPENAI_API_KEY', '')).strip()
    if not raw:
        raw = os.environ.get('OPENAI_API_KEY', '').strip()
    if not raw:
        return None
    if any(c.isspace() for c in raw):
        raise ConfigurationError('API key contains whitespace. Paste the key again.')
    return Credentials(api_key=SecretStr(raw))


def load_settings() -> Settings:
    """Model choice stays explicit; this module does not assume model availability."""
    model = os.environ.get('OPENAI_MODEL', '').strip()
    if not model:
        raise ConfigurationError('Choose an API model or set OPENAI_MODEL before loading settings.')
    return Settings(model=model)


T = TypeVar('T', bound=BaseModel)


def load_json(path: Path, schema: type[T] | None = None) -> T | dict[str, Any]:
    """Load UTF-8 JSON; fail visibly on absent, invalid or non-object documents."""
    try:
        def reject_constant(value: str) -> None:
            raise ValueError('Nonfinite JSON number')
        data = json.loads(path.read_text(encoding='utf-8'), parse_constant=reject_constant)
    except (OSError, UnicodeError, ValueError):
        raise ConfigurationError(f'Cannot read valid JSON from {path.name}.') from None
    if not isinstance(data, dict):
        raise ConfigurationError(f'{path.name} must contain a JSON object.')
    if schema is None:
        return data
    try:
        return schema.model_validate(data)
    except ValueError:
        # Validation errors can include raw inputs: do not forward them to logs/UI.
        raise ConfigurationError(f'{path.name} does not match its required schema.') from None


PUBLIC_FILES = frozenset({'rates_pk.json', 'bylaws.json', 'labour_rates.json',
                          'model_pricing.json', 'calendar_exceptions.json'})


def read_public_config(filename: str, schema: type[T] | None = None) -> T | dict[str, Any]:
    if filename not in PUBLIC_FILES:
        raise ConfigurationError('Unknown public configuration file.')
    return load_json(DATA_DIR / filename, schema)


def save_public_config(filename: str, value: T, *, enabled: bool = False) -> None:
    """Atomic local single-user edit. Callers must pass a validated typed model.

    Not a multi-user store or concurrency lock. Hosted deployments must supply
    authenticated, versioned project persistence instead of enabling this route.
    """
    if not enabled:
        raise ConfigurationError('Local settings writes are disabled.')
    if filename not in PUBLIC_FILES:
        raise ConfigurationError('Unknown public configuration file.')
    if not isinstance(value, BaseModel) or isinstance(value, Credentials):
        raise ConfigurationError('A validated public configuration model is required.')
    try:
        # Revalidate nested mutations before writing. Never accept arbitrary dictionaries.
        checked = type(value).model_validate(value.model_dump(mode='json'))
        payload = checked.model_dump_json(indent=2)
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=DATA_DIR,
                                             prefix='.settings-', suffix='.json', delete=False) as f:
                temporary = Path(f.name)
                f.write(payload + '\n')
                f.flush()
                os.fsync(f.fileno())
            os.replace(temporary, DATA_DIR / filename)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
    except (OSError, ValueError):
        raise ConfigurationError(f'Unable to save {filename}.') from None


def downstream_stages(changed: Stage) -> set[Stage]:
    """Return transitive dependants, excluding the changed stage itself."""
    found: set[Stage] = set()
    stack = list(DEPENDENCIES[changed])
    while stack:
        stage = stack.pop()
        if stage not in found:
            found.add(stage)
            stack.extend(DEPENDENCIES[stage])
    return found


def feet_to_metres(value: float) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError('Feet must be numeric.')
    import math
    if not math.isfinite(value) or value < 0:
        raise ValueError('Feet must be finite and nonnegative.')
    return value * .3048


def sqft_to_m2(value: float) -> float:
    """Convert area, applying the same input validity rule as linear conversion."""
    return feet_to_metres(value) * .3048
