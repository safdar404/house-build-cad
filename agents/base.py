"""Bounded, session-local OpenAI structured-output agent foundation.

The orchestrator (delivered separately) owns specialist function dispatch.
This module never executes model-generated code or logs request contents.
"""
from __future__ import annotations

import json
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Generic, TypeVar

from openai import (APIConnectionError, APIStatusError, APITimeoutError,
                    AuthenticationError, OpenAI, PermissionDeniedError,
                    RateLimitError, pydantic_function_tool)
from pydantic import BaseModel, ValidationError

from config import Credentials, Settings
from schemas import Usage

T = TypeVar('T', bound=BaseModel)


class AgentError(RuntimeError):
    """Safe, user-facing error without API response bodies or credentials."""


class InvalidAgentOutput(ValueError):
    """A semantic output check failed; never forward its raw message to the API."""


@dataclass(frozen=True)
class AgentResult(Generic[T]):
    value: T
    usage: tuple[Usage, ...]
    attempts: int


def _strict_load(text: str) -> object:
    def bad_constant(value: str) -> None:
        raise ValueError('Nonfinite JSON is not permitted.')
    def unique_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for k, v in pairs:
            if k in result:
                raise ValueError('Duplicate JSON keys are not permitted.')
            result[k] = v
        return result
    return json.loads(text, parse_constant=bad_constant, object_pairs_hook=unique_keys)


class BaseAgent(Generic[T]):
    """One validated specialist; instantiate per user session.

    `usage_log` is a caller-owned session list. It captures usage before output
    validation, including refused, truncated and retried responses when supplied
    by the service. Network failures may incur unreported server-side usage.
    No automatic price is claimed: pricing.py will price these records later.
    """
    def __init__(self, *, settings: Settings, credentials: Credentials,
                 output_schema: type[T], system_prompt: str,
                 usage_log: list[Usage] | None = None,
                 client: OpenAI | None = None,
                 sleeper: Callable[[float], None] = time.sleep) -> None:
        self.settings = settings.model_copy(deep=True)
        self.output_schema = output_schema
        self.system_prompt = system_prompt
        self.usage_log = usage_log if usage_log is not None else []
        self._secret = credentials.api_key.get_secret_value()
        # Disable SDK retries so the outer attempt bound is the true call bound.
        self._owns_client = client is None
        self._client = client or OpenAI(api_key=self._secret, max_retries=0,
                                       timeout=settings.timeout_seconds)
        self._sleep = sleeper

    def close(self) -> None:
        if self._owns_client:
            self._client.close()
        self._secret = ''

    def _record_usage(self, response: object) -> Usage | None:
        raw = getattr(response, 'usage', None)
        if raw is None:
            return None
        details = getattr(raw, 'input_tokens_details', None)
        entry = Usage(model=getattr(response, 'model', None) or self.settings.model,
                      input_tokens=raw.input_tokens, output_tokens=raw.output_tokens,
                      cached_input_tokens=getattr(details, 'cached_tokens', 0) or 0)
        self.usage_log.append(entry)
        return entry

    def run(self, messages: Sequence[dict[str, str]], *,
            validate: Callable[[T], T] | None = None) -> AgentResult[T]:
        """Return validated JSON, with bounded transport/output retries.

        User history is restricted to user/assistant roles. Keys pasted into chat
        are rejected before transmission. No prompt/response is written to disk.
        """
        history: list[dict[str, str]] = []
        total_chars = 0
        for message in messages:
            if set(message) != {'role', 'content'} or message['role'] not in {'user', 'assistant'}:
                raise AgentError('Conversation contains an unsupported message.')
            content = message['content']
            if not isinstance(content, str):
                raise AgentError('Conversation content must be text.')
            if self._secret and self._secret in content:
                raise AgentError('Remove the API key from the conversation; use the password sidebar.')
            total_chars += len(content)
            history.append(dict(message))
        if not history or total_chars > 120_000:
            raise AgentError('Conversation is empty or too large. Start a shorter interview.')
        # Public SDK helper produces the strict schema expected by the API.
        schema = pydantic_function_tool(self.output_schema)['function']['parameters']
        records: list[Usage] = []
        feedback = ''
        for attempt in range(self.settings.max_retries + 1):
            try:
                response = self._client.responses.create(
                    model=self.settings.model,
                    instructions=self.system_prompt + feedback,
                    input=history,
                    text={'format': {'type': 'json_schema', 'name': self.output_schema.__name__,
                                     'strict': True, 'schema': schema}},
                    max_output_tokens=self.settings.max_output_tokens,
                    store=False,
                )
                usage = self._record_usage(response)
                if usage is not None:
                    records.append(usage)
                for item in getattr(response, 'output', []):
                    for part in getattr(item, 'content', []):
                        if getattr(part, 'type', '') == 'refusal':
                            raise AgentError('The model declined this request. Revise the requirements.')
                if getattr(response, 'status', None) != 'completed':
                    raise AgentError('The response was incomplete. Increase the output limit or shorten the brief.')
                text = response.output_text
                if self._secret and self._secret in text:
                    raise AgentError('The response contained sensitive text and was discarded.')
                parsed = _strict_load(text)
                value = self.output_schema.model_validate(parsed)
                if validate is not None:
                    value = validate(value)
                return AgentResult(value=value, usage=tuple(records), attempts=attempt+1)
            except AuthenticationError:
                raise AgentError('API key authentication failed. Check the password sidebar.') from None
            except PermissionDeniedError:
                raise AgentError('This API key cannot access the selected model or project.') from None
            except RateLimitError as exc:
                if getattr(exc, 'code', None) == 'insufficient_quota':
                    raise AgentError('API quota is exhausted. Check API billing and project limits.') from None
                if attempt == self.settings.max_retries:
                    raise AgentError('API rate limit reached. Try again later.') from None
                self._sleep(min(2**attempt, 8))
            except (APIConnectionError, APITimeoutError):
                if attempt == self.settings.max_retries:
                    raise AgentError('Could not reach the API within the configured timeout.') from None
                self._sleep(min(2**attempt, 8))
            except APIStatusError as exc:
                if exc.status_code >= 500 and attempt < self.settings.max_retries:
                    self._sleep(min(2**attempt, 8))
                    continue
                raise AgentError('API request failed. Check model support, access and configuration.') from None
            except (ValidationError, ValueError) as exc:
                if not isinstance(exc, (ValidationError, InvalidAgentOutput, json.JSONDecodeError)):
                    # _strict_load can raise ordinary ValueError for duplicate keys.
                    feedback = '\nReturn valid JSON without duplicate keys or nonfinite values.'
                else:
                    feedback = '\nYour previous output failed local validation. Recheck all required fields, units and constraints; return corrected JSON.'
                if attempt == self.settings.max_retries:
                    raise AgentError('The model output failed validation after the allowed attempts.') from None
        raise AgentError('No valid response was returned.')

