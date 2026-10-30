from emoji_picker.catalog import CATEGORY_ORDER, EmojiCatalog, EmojiRecord, strip_skin_tones


def small_catalog():
    return EmojiCatalog(
        [
            EmojiRecord("😀", "grinning face", "Smileys & Emotion", ("face", "smile")),
            EmojiRecord("👍", "thumbs up", "People & Body", ("hand", "like")),
            EmojiRecord("👍🏻", "thumbs up: light skin tone", "People & Body", ("hand", "like")),
            EmojiRecord("🍎", "red apple", "Food & Drink", ("fruit", "food")),
            EmojiRecord("🏻", "light skin tone", "Component", ("skin",)),
        ]
    )


def test_system_catalog_loads():
    catalog = EmojiCatalog.load()
    assert len(catalog.all_records) > 3000
    assert catalog.get("😀").description == "grinning face"
    assert set(CATEGORY_ORDER).issubset(catalog.categories)


def test_skin_tone_variants_are_collapsed_for_browsing():
    catalog = small_catalog()
    assert strip_skin_tones("👍🏻") == "👍"
    assert catalog.get("👍").variants == ("👍🏻",)
    assert catalog.get("👍🏻").is_skin_tone_variant
    assert "👍🏻" not in [item.value for item in catalog.browse_records]
    assert "🏻" not in [item.value for item in catalog.browse_records]


def test_search_matches_description_and_keyword():
    catalog = small_catalog()
    assert catalog.search("apple")[0].value == "🍎"
    assert catalog.search("fruit")[0].value == "🍎"
    assert catalog.search("grinning face")[0].value == "😀"


def test_tone_search_returns_exact_variant():
    catalog = small_catalog()
    assert [item.value for item in catalog.search("light skin tone")] == ["👍🏻"]


def test_exact_match_ranks_ahead_of_keyword_match():
    catalog = EmojiCatalog(
        [
            EmojiRecord("A", "alpha", "Symbols", ("target",)),
            EmojiRecord("B", "target", "Symbols", ("letter",)),
        ]
    )
    assert catalog.search("target")[0].value == "B"

