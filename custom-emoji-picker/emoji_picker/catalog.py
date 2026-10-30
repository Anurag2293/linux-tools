"""Load and search the emoji metadata shipped with IBus."""

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import gi

gi.require_version("IBus", "1.0")
from gi.repository import IBus


DEFAULT_CATALOG = Path("/usr/share/ibus/dicts/emoji-en.dict")
SKIN_TONE_SEQUENCE = tuple(chr(codepoint) for codepoint in range(0x1F3FB, 0x1F400))
SKIN_TONES = frozenset(SKIN_TONE_SEQUENCE)
SKIN_TONE_WORDS = (
    "skin tone",
    "light skin",
    "medium-light",
    "medium skin",
    "medium-dark",
    "dark skin",
)

CATEGORY_ORDER: Tuple[str, ...] = (
    "Smileys & Emotion",
    "People & Body",
    "Animals & Nature",
    "Food & Drink",
    "Travel & Places",
    "Activities",
    "Objects",
    "Symbols",
    "Flags",
)


@dataclass(frozen=True)
class EmojiRecord:
    """Searchable metadata for one exact Unicode emoji sequence."""

    value: str
    description: str
    category: str
    keywords: Tuple[str, ...]
    variants: Tuple[str, ...] = ()
    base_value: str = ""

    @property
    def is_skin_tone_variant(self) -> bool:
        return bool(self.base_value and self.base_value != self.value)


def strip_skin_tones(value: str) -> str:
    """Return the sequence with Fitzpatrick modifiers removed."""

    return "".join(character for character in value if character not in SKIN_TONES)


class EmojiCatalog:
    """In-memory catalog with collapsed browsing and ranked search."""

    def __init__(self, records: Sequence[EmojiRecord]):
        by_value: Dict[str, EmojiRecord] = {}
        for record in records:
            by_value.setdefault(record.value, record)

        variant_values: Dict[str, List[str]] = {}
        normalized: Dict[str, EmojiRecord] = {}
        for value, record in by_value.items():
            base_value = strip_skin_tones(value)
            if base_value != value and base_value in by_value:
                variant_values.setdefault(base_value, []).append(value)
                normalized[value] = replace(record, base_value=base_value)
            else:
                normalized[value] = replace(record, base_value=value)

        tone_order = {character: index for index, character in enumerate(SKIN_TONE_SEQUENCE)}

        def variant_sort_key(value: str) -> Tuple[int, ...]:
            positions = tuple(tone_order[character] for character in value if character in tone_order)
            return positions or (99,)

        for base_value, variants in variant_values.items():
            normalized[base_value] = replace(
                normalized[base_value],
                variants=tuple(sorted(variants, key=variant_sort_key)),
            )

        self.by_value: Mapping[str, EmojiRecord] = normalized
        self.all_records: Tuple[EmojiRecord, ...] = tuple(normalized.values())
        self.browse_records: Tuple[EmojiRecord, ...] = tuple(
            record
            for record in self.all_records
            if not record.is_skin_tone_variant and record.category != "Component"
        )
        self.categories: Mapping[str, Tuple[EmojiRecord, ...]] = {
            category: tuple(record for record in self.browse_records if record.category == category)
            for category in CATEGORY_ORDER
        }

    @classmethod
    def load(cls, path: Path = DEFAULT_CATALOG) -> "EmojiCatalog":
        if not path.is_file():
            raise FileNotFoundError("IBus emoji dictionary was not found: {}".format(path))

        IBus.init()
        ibus_rows = IBus.EmojiData.load(str(path))
        records = [
            EmojiRecord(
                value=row.get_emoji(),
                description=(row.get_description() or row.get_emoji()).strip(),
                category=(row.get_category() or "Symbols").strip(),
                keywords=tuple(
                    dict.fromkeys(
                        annotation.strip()
                        for annotation in row.get_annotations()
                        if annotation and annotation.strip()
                    )
                ),
            )
            for row in ibus_rows
            if row.get_emoji()
        ]
        return cls(records)

    def get(self, value: str) -> Optional[EmojiRecord]:
        return self.by_value.get(value)

    def records_for_values(self, values: Iterable[str]) -> List[EmojiRecord]:
        return [self.by_value[value] for value in values if value in self.by_value]

    def for_category(self, category: str) -> Tuple[EmojiRecord, ...]:
        return self.categories.get(category, ())

    def search(
        self,
        query: str,
        favorites: Sequence[str] = (),
        recents: Sequence[str] = (),
        limit: int = 240,
    ) -> List[EmojiRecord]:
        normalized_query = " ".join(query.casefold().split())
        if not normalized_query:
            return []

        tokens = normalized_query.split()
        wants_tone = any(word in normalized_query for word in SKIN_TONE_WORDS)
        pool = (
            tuple(record for record in self.all_records if record.category != "Component")
            if wants_tone
            else self.browse_records
        )
        favorite_rank = {value: index for index, value in enumerate(favorites)}
        recent_rank = {value: index for index, value in enumerate(recents)}
        scored = []

        for original_index, record in enumerate(pool):
            description = record.description.casefold()
            keywords = tuple(keyword.casefold() for keyword in record.keywords)
            searchable = " ".join((description,) + keywords)
            if not all(token in searchable for token in tokens):
                continue

            if description == normalized_query:
                match_rank = 0
            elif description.startswith(normalized_query):
                match_rank = 1
            elif any(keyword == normalized_query for keyword in keywords):
                match_rank = 2
            elif any(keyword.startswith(normalized_query) for keyword in keywords):
                match_rank = 3
            else:
                match_rank = 4

            preference_rank = min(
                favorite_rank.get(record.value, 10_000),
                recent_rank.get(record.value, 10_000),
            )
            scored.append(
                (
                    match_rank,
                    preference_rank,
                    len(record.description),
                    original_index,
                    record,
                )
            )

        scored.sort(key=lambda item: item[:-1])
        return [item[-1] for item in scored[:limit]]
