"""One adapter over every provider, and the factory that builds it.

Groq, OpenAI and Anthropic differ in base URL, model name and price. None of
those differences belongs in an agent, so they are resolved here and the rest
of the system sees only `ChatModel`.
"""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING, Any, Protocol, TypeVar, cast

from autogen_core.models import CreateResult, ModelFamily, ModelInfo, UserMessage
from pydantic import BaseModel

from augury.core.adapters.base import ChatModel, Completion, ModelSpec, Usage
from augury.core.adapters.cassette import CassetteMiss
from augury.core.adapters.pricing import Pricing, pricing_for
from augury.core.adapters.retry import (
    MAX_DELAY_SECONDS,
    RateLimited,
    retry_after,
)

if TYPE_CHECKING:  # Settings imports this module's siblings; keep it one-way.
    from augury.core.settings import Settings

__all__ = [
    "MODEL_CAPABILITIES",
    "CompletionClient",
    "Pricing",
    "ProviderAdapter",
    "SealedModel",
    "build_model",
    "model_from",
]

T = TypeVar("T", bound=BaseModel)

# A model asked for structured output occasionally returns the schema instead
# of an instance, or JSON the provider rejects outright. Losing a whole case to
# that would be a harness failure reported as a reviewer failure. Bounded,
# because a model that cannot produce the schema will not start doing so.
MAX_ATTEMPTS = 3

# How many times one call will wait out a rate limit before giving up. Groq
# allows 250,000 tokens a minute, and a concurrent review of a real backend
# exceeds that routinely -- a full run died on its ninth module before this
# existed, losing everything already paid for.
MAX_RATE_LIMIT_WAITS = 8

# Added per wait so concurrent callers do not all wake at the same instant and
# re-trigger the limit together.
JITTER_SECONDS = 0.25

CORRECTION = (
    "\n\nYour previous response was rejected: {error}\n\n"
    "Return only the JSON instance. Do not return the schema itself: no "
    "`$defs`, no `properties`, no `required`, no `title`, no `type`. Emit only "
    "the described fields and their values."
)


TOO_LONG = (
    "\n\nYour previous response was cut off before it ended: {error}\n\n"
    "It was not malformed -- it ran past the output limit. Return the same "
    "kind of answer with fewer findings: keep only the most severe, and make "
    "each explanation shorter. A complete answer about three problems is worth "
    "more than a truncated one about ten."
)

NOTHING_BACK = (
    "\n\nYour previous response was empty: {error}\n\n"
    "Finding nothing is a valid answer, but it has to be written down. Reply "
    "with the json object anyway and leave the list empty -- for example "
    '{{"findings": []}} -- rather than replying with no content at all.'
)

# What a JSON parser says when the document simply stopped. Distinguishing
# this from a schema mismatch is the whole point: they need opposite advice.
_RAN_OUT = ("eof while parsing", "unexpected end of", "eof expected")


# DeepSeek allows 384K output tokens; the others allow far less, and a
# ceiling nobody reaches costs nothing. This is a backstop against a loop
# that keeps asking for more, not a target.
MOST_TOKENS = 64_000


def _more_room(current: int) -> int:
    """Twice what was not enough, up to a ceiling worth stopping at."""
    return min(max(current, 1) * 2, MOST_TOKENS)


def ran_out_of_room(error: str) -> bool:
    """Whether this failure is a cut-off answer rather than a wrong one."""
    said = error.lower()
    return any(phrase in said for phrase in _RAN_OUT)


def correction_for(error: str) -> str:
    """The advice that addresses what actually went wrong.

    Telling a model whose answer was truncated to stop returning the schema is
    advice about a mistake it did not make, and it makes the identical mistake
    again -- which is how one module consumed three attempts and ended a run.
    """
    if "empty response" in error.lower():
        template = NOTHING_BACK
    elif ran_out_of_room(error):
        template = TOO_LONG
    else:
        template = CORRECTION
    return template.format(error=error)


class CompletionClient(Protocol):
    """The only part of a provider client this adapter depends on.

    Narrower than autogen's `ChatCompletionClient` on purpose: depending on the
    whole interface would mean a test double has to implement all of it.
    """

    async def create(self, messages: Any, **kwargs: Any) -> CreateResult: ...


# Groq is OpenAI-compatible, so it is a base URL rather than a third client.
OPENAI_COMPATIBLE_BASE_URLS: dict[str, str | None] = {
    "openai": None,
    "groq": "https://api.groq.com/openai/v1",
    "deepseek": "https://api.deepseek.com",
}


# Providers whose API accepts a named JSON schema and decodes against it.
# Anything absent is asked for a JSON object instead, because a 400 on the
# first model call is a worse default than a schema in the prompt.
STRICT_DECODERS = frozenset({"openai", "groq", "anthropic"})


def wants_named_schema(provider: str) -> bool:
    """Whether this provider accepts a schema-shaped response_format."""
    return provider in STRICT_DECODERS


def schema_in_prompt(prompt: str, schema: type[BaseModel]) -> str:
    """The prompt, followed by the shape the answer has to take.

    DeepSeek's JSON mode documents two requirements: the word "json" must
    appear in the prompt, and it must "provide an example of the desired JSON
    format". Both are met here rather than assumed -- a schema dump mentions
    JSON only incidentally, and a model without strict decoding follows an
    example more reliably than a `$defs` block.
    """
    shape = json.dumps(schema.model_json_schema(), indent=2, sort_keys=True)
    return (
        f"{prompt}\n\n"
        "Reply with one json object and nothing else: no prose, no code fence, "
        "no explanation, and never the schema itself.\n\n"
        f"It must match this schema:\n{shape}\n\n"
        f"An answer of this shape looks like:\n{_example_of(schema)}"
    )


def _example_of(schema: type[BaseModel]) -> str:
    """A skeleton instance, showing field names in place rather than described."""
    fields = schema.model_json_schema().get("properties", {})
    lines = [f'  "{name}": {_placeholder(spec)}' for name, spec in fields.items()]
    return "{\n" + ",\n".join(lines) + "\n}"


def _placeholder(spec: dict[str, object]) -> str:
    kind = spec.get("type")
    if kind == "array":
        return "[...]"
    if kind == "object":
        return "{...}"
    if kind == "integer":
        return "0"
    if kind == "number":
        return "0.0"
    if kind == "boolean":
        return "false"
    return '"..."'


def came_back_empty(content: str) -> bool:
    """Whether the provider answered with nothing.

    DeepSeek documents this: "the API may occasionally return empty content".
    Handed to a JSON parser it becomes "expecting value at line 1", which reads
    like a malformed answer and earns advice about formatting -- for a response
    that had no formatting to get wrong.
    """
    return not content.strip()


class ProviderAdapter:
    """Turns a provider response into a validated object and a measured cost."""

    def __init__(
        self,
        client: CompletionClient,
        *,
        model_id: str,
        pricing: Pricing,
        provider: str = "",
        max_tokens: int = 0,
    ) -> None:
        self._client = client
        self._model_id = model_id
        self._pricing = pricing
        self._provider = provider
        self._max_tokens = max_tokens
        self._usage = Usage()
        self._last_attempt_cost = Usage()
        self.retries = 0
        self.rate_limited = 0

    @property
    def model_id(self) -> str:
        return self._model_id

    @property
    def usage(self) -> Usage:
        """Cumulative for the life of this adapter, matching provider SDKs."""
        return self._usage

    async def structured(self, *, prompt: str, schema: type[T]) -> T:
        """The validated object alone, for callers that do not need the cost."""
        completion = await self.call(prompt=prompt, schema=schema)
        return cast("T", completion.result)

    async def _wait_out(self, error: Exception, waited: int) -> bool:
        """Sleep off a rate limit. False once this call has waited enough.

        `waited` is the count for *this call*, not for the adapter. One adapter
        serves a whole review, so a lifetime budget is spent within the first
        few modules and every 429 after that is fatal -- which is exactly how a
        full-coverage run died at module eight with this logic in place.
        """
        if waited >= MAX_RATE_LIMIT_WAITS:
            return False
        asked = retry_after(str(error))
        delay = asked if asked is not None else min(2.0**waited, MAX_DELAY_SECONDS)
        self.rate_limited += 1
        await asyncio.sleep(delay + JITTER_SECONDS * (waited + 1))
        return True

    async def call(self, *, prompt: str, schema: type[T]) -> Completion:
        """Ask for the schema, not for JSON in prose, and validate the answer.

        A response that does not match is raised rather than repaired: a
        half-populated finding flowing downstream is worse than a loud failure.
        """
        last: Exception | None = None
        attempt_prompt = prompt
        spent = Usage()

        # A while loop, not `for attempt in range(MAX_ATTEMPTS)`. The previous
        # version said in a comment that a rate limit does not count against
        # the attempts and then used `continue`, which advances the counter --
        # so three consecutive 429s exhausted the loop and killed a
        # full-coverage run at module nine. The comment was right about what
        # should happen and the code did the opposite.
        attempt = 0
        waited = 0
        # Raised only when the provider says the answer was cut off. A
        # reasoning model spends this budget thinking before it writes, so a
        # ceiling that fits the answer may not fit the thinking, and advice to
        # be brief does not create room that is not there.
        ceiling = 0
        while attempt < MAX_ATTEMPTS:
            try:
                result, cost = await self._attempt(attempt_prompt, schema, ceiling=ceiling)
                # A rejected attempt still consumed tokens, so the cost of this
                # call is every attempt it took, not only the one that worked.
                return Completion(result=result, usage=spent + cost, retries=attempt)
            except Exception as error:  # provider rejection, rate limit, bad JSON
                # A rate limit is a wait, not a failure. It consumed no tokens
                # and the same prompt will succeed shortly, so it does not
                # count against MAX_ATTEMPTS and the prompt is not "corrected"
                # -- correcting a prompt that was never read is how a transient
                # 429 turns into three wasted calls and then a lost run.
                if RateLimited.looks_like(str(error)) and await self._wait_out(error, waited):
                    waited += 1
                    continue  # `attempt` deliberately unchanged
                    # Waited as long as this is willing to. Fall through and
                    # treat it as a failure, so the run ends saying why rather
                    # than waiting forever.
                last = error
                spent = spent + self._last_attempt_cost
                # Counted only when another attempt will follow: three attempts
                # is two retries, and reporting three implies a fourth call
                # that was never made.
                if attempt < MAX_ATTEMPTS - 1:
                    self.retries += 1
                attempt += 1
                # Repeating an identical prompt to a deterministic model
                # repeats the identical failure, so the retry has to differ.
                if ran_out_of_room(_summarise(error)):
                    ceiling = _more_room(ceiling or self._max_tokens)
                attempt_prompt = prompt + correction_for(_summarise(error))

        assert last is not None  # the loop either returned or recorded an error
        raise last

    async def _attempt(self, prompt: str, schema: type[T], *, ceiling: int = 0) -> tuple[T, Usage]:
        # DeepSeek answers 400 to the schema-shaped response_format the others
        # accept, so it is asked for a JSON object and shown the schema in the
        # prompt instead. What comes back is validated identically either way.
        named = wants_named_schema(self._provider)
        # Only a call that already ran out of room asks for more; a normal one
        # keeps the configured budget so the cost of a review stays predictable.
        extra = {"max_tokens": ceiling} if ceiling else {}
        response = await self._client.create(
            messages=[
                UserMessage(
                    content=prompt if named else schema_in_prompt(prompt, schema),
                    source="augury",
                )
            ],
            json_output=schema if named else True,
            extra_create_args=extra,
        )
        cost = self._record(response.usage)

        # The provider says why it stopped. A reasoning model spends the output
        # budget thinking before it answers, so an overflow arrives as empty
        # content with finish_reason="length" -- and guessing from the parse
        # error instead blamed the provider for an "occasional" empty response
        # that was neither occasional nor its fault.
        if response.finish_reason == "length":
            raise ValueError(
                f"{self._model_id} hit the output limit before finishing: "
                "EOF while parsing the answer. Reasoning tokens are spent from "
                "the same budget as the answer"
            )

        content = response.content
        if isinstance(content, str) and came_back_empty(content):
            raise ValueError(
                f"{self._model_id} returned an empty response, which its provider "
                "documents as an occasional fault; the same prompt usually succeeds"
            )
        if not isinstance(content, str):
            raise TypeError(f"expected text from {self._model_id}, got {type(content).__name__}")
        return schema.model_validate_json(content), cost

    def _record(self, usage: object) -> Usage:
        """Add this attempt to the running total and return what it cost.

        Returning the cost is what lets a call report its own price. Reading
        the cumulative total before and after does not work once calls run
        concurrently: every sibling that finished first lands inside the delta.
        """
        prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
        completion_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
        cost = Usage(
            input_tokens=prompt_tokens,
            output_tokens=completion_tokens,
            usd=self._pricing.cost(input_tokens=prompt_tokens, output_tokens=completion_tokens),
        )
        self._usage = self._usage + cost
        self._last_attempt_cost = cost
        return cost


def build_model(spec: ModelSpec, *, api_key: str) -> ChatModel:
    """Resolve a declarative spec into a live adapter.

    Pricing is looked up first so an unpriced model fails here, before a run
    starts, rather than reporting itself as free at the end of one.
    """
    pricing = pricing_for(spec.model)

    if spec.provider in OPENAI_COMPATIBLE_BASE_URLS:
        from autogen_ext.models.openai import OpenAIChatCompletionClient

        base_url = OPENAI_COMPATIBLE_BASE_URLS[spec.provider]
        # cast because autogen's client declares `create` with named keyword
        # parameters rather than **kwargs, so it does not structurally satisfy
        # a Protocol written that way. It does provide what we call.
        client: CompletionClient = cast(
            "CompletionClient",
            OpenAIChatCompletionClient(
                model=spec.model,
                api_key=api_key,
                temperature=spec.temperature,
                max_tokens=spec.max_tokens,
                model_info=MODEL_CAPABILITIES,
                base_url=base_url,
            )
            if base_url
            else OpenAIChatCompletionClient(
                model=spec.model,
                api_key=api_key,
                temperature=spec.temperature,
                max_tokens=spec.max_tokens,
                model_info=MODEL_CAPABILITIES,
            ),
        )
    else:
        from autogen_ext.models.anthropic import AnthropicChatCompletionClient

        client = cast(
            "CompletionClient",
            AnthropicChatCompletionClient(
                model=spec.model,
                api_key=api_key,
                temperature=spec.temperature,
                max_tokens=spec.max_tokens,
                model_info=MODEL_CAPABILITIES,
            ),
        )

    return ProviderAdapter(
        client,
        model_id=spec.model,
        pricing=pricing,
        provider=spec.provider,
        max_tokens=spec.max_tokens,
    )


# Declared rather than looked up. Groq's models have no entry in autogen's
# registry at all, and every model this project uses is driven the same way:
# text in, structured output back, no vision. Stating it keeps a new model from
# being refused for want of a registry entry.
MODEL_CAPABILITIES: ModelInfo = {
    "vision": False,
    "function_calling": True,
    "json_output": True,
    "structured_output": True,
    "family": ModelFamily.UNKNOWN,
    "multiple_system_messages": True,
}


def _summarise(error: Exception) -> str:
    """Enough of the provider's complaint to be actionable, not the whole dump."""
    return str(error)[:400]


def model_from(settings: Settings) -> ChatModel:
    """The model every entrypoint should build. Takes Settings, not a spec.

    `build_model` needs a spec and a key, so a caller that forgets replay mode
    gets a live client and quietly spends money. That failure has already
    happened in this project once, with experiment conditions: three call
    sites, one of them updated, a green suite, and a published number produced
    by a command nobody had actually run.

    The fix is a signature that cannot be called wrongly. Everything that
    decides between live, recording and replay is decided here, once, and
    `tests/test_model_from_settings.py` fails if anything reaches past it.
    """
    from augury.core.adapters.cassette import CassetteModel

    if not (settings.replay_only or settings.record):
        return build_model(settings.spec, api_key=settings.api_key)

    directory = settings.cassette_dir
    if directory is None:  # pragma: no cover - load_settings always resolves one
        raise ValueError("a cassette directory is required to record or replay")

    # Replay never reaches a provider, so it must not need a client to exist:
    # the OpenAI client refuses to construct without a key, which is precisely
    # the situation a judge cloning this repository is in.
    inner: ChatModel = (
        SealedModel(settings.spec.model)
        if settings.replay_only
        else build_model(settings.spec, api_key=settings.api_key)
    )
    return CassetteModel(inner, directory, replay_only=settings.replay_only)


class SealedModel:
    """A model that carries an identity and refuses to be called.

    Used as the inner model in replay, where every answer comes from a
    recording. If a call ever reaches it, a cassette is missing and the run
    must stop saying so rather than fall through to a provider.
    """

    def __init__(self, model_id: str) -> None:
        self._model_id = model_id
        self._usage = Usage()

    @property
    def model_id(self) -> str:
        return self._model_id

    @property
    def usage(self) -> Usage:
        return self._usage

    async def structured(self, *, prompt: str, schema: type[T]) -> T:
        raise CassetteMiss(self._refusal())

    async def call(self, *, prompt: str, schema: type[T]) -> Completion:
        raise CassetteMiss(self._refusal())

    def _refusal(self) -> str:
        return (
            f"replay is on and no recording covers this call to {self._model_id}. "
            "The cassette set is incomplete for this run. Re-record with "
            "AUGURY_RECORD=1 and a provider key, or check AUGURY_CASSETTES."
        )
