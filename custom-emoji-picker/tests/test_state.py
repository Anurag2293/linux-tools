import json

from emoji_picker.state import MAX_RECENTS, PickerState


def test_favorites_and_recents_persist(tmp_path):
    path = tmp_path / "state.json"
    state = PickerState(path)
    assert state.toggle_favorite("😀") is True
    state.add_recent("😀")
    state.add_recent("🎉")

    restored = PickerState(path)
    assert restored.favorites == ["😀"]
    assert restored.recents == ["🎉", "😀"]
    assert restored.toggle_favorite("😀") is False


def test_recents_are_unique_and_bounded(tmp_path):
    state = PickerState(tmp_path / "state.json")
    for index in range(MAX_RECENTS + 10):
        state.add_recent("emoji-{}".format(index))
    state.add_recent("emoji-35")
    assert len(state.recents) == MAX_RECENTS
    assert state.recents[0] == "emoji-35"
    assert len(set(state.recents)) == len(state.recents)


def test_malformed_state_is_backed_up(tmp_path):
    path = tmp_path / "state.json"
    path.write_text("not json", encoding="utf-8")
    state = PickerState(path)
    assert state.favorites == []
    assert state.recents == []
    assert not path.exists()
    assert len(list(tmp_path.glob("state.corrupt-*.json"))) == 1


def test_invalid_entries_are_cleaned(tmp_path):
    path = tmp_path / "state.json"
    path.write_text(
        json.dumps({"favorites": ["😀", "😀", None, ""], "recents": "bad"}),
        encoding="utf-8",
    )
    state = PickerState(path)
    assert state.favorites == ["😀"]
    assert state.recents == []

