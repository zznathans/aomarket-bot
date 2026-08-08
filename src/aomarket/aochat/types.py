from dataclasses import dataclass


@dataclass(frozen=True)
class CharacterInfo:
    id: int
    name: str
    level: int
    online: int


@dataclass(frozen=True)
class InboundTell:
    sender_id: int
    message: str


@dataclass(frozen=True)
class InboundPrivgroupMessage:
    sender_id: int
    message: str


@dataclass(frozen=True)
class BuddyStatus:
    char_id: int
    online: bool
