"""Small data contracts shared by parsers, execution, and reporting."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, AsyncIterator, Iterable, Protocol

Metadata = dict[str, Any]


@dataclass(frozen=True)
class ParsedDocument:
    markdown: str
    metadata: Metadata = field(default_factory=dict)


@dataclass(frozen=True)
class DocumentOutcome:
    path: Path
    document: ParsedDocument | None = None
    error: str | None = None
    duration_seconds: float | None = None


@dataclass(frozen=True)
class ExecutionOptions:
    timeout: int = 7200
    concurrency: int = 5

    def __post_init__(self) -> None:
        if self.timeout < 1 or self.concurrency < 1:
            raise ValueError("Timeout and concurrency must be positive")


class AsyncParser(Protocol):
    @property
    def config(self) -> Metadata: ...

    async def convert(self, path: Path) -> ParsedDocument: ...


class SequentialParser(Protocol):
    @property
    def config(self) -> Metadata: ...

    def convert(self, path: Path) -> ParsedDocument: ...


class BatchParser(Protocol):
    @property
    def config(self) -> Metadata: ...

    def convert_many(self, paths: list[Path]) -> Iterable[DocumentOutcome]: ...


class AsyncBatchParser(Protocol):
    @property
    def config(self) -> Metadata: ...

    def convert_many(self, paths: list[Path]) -> AsyncIterator[DocumentOutcome]: ...
