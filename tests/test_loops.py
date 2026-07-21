from clipcara.loops import LoopStore


def test_add_list_remove(tmp_path):
    store = LoopStore(str(tmp_path / "loops.json"))
    store.add("/audio/a.wav", "verse", 1000, 5000)
    store.add("/audio/a.wav", "chorus", 6000, 9000)
    store.add("/audio/b.wav", "intro", 0, 2000)

    loops = store.loops_for("/audio/a.wav")
    assert [l["name"] for l in loops] == ["verse", "chorus"]
    assert loops[0] == {"name": "verse", "a": 1000, "b": 5000}

    store.remove("/audio/a.wav", "verse")
    assert [l["name"] for l in store.loops_for("/audio/a.wav")] == ["chorus"]
    assert store.loops_for("/audio/b.wav") == [{"name": "intro", "a": 0,
                                                "b": 2000}]


def test_same_name_replaces(tmp_path):
    store = LoopStore(str(tmp_path / "loops.json"))
    store.add("/audio/a.wav", "verse", 1000, 5000)
    store.add("/audio/a.wav", "verse", 1100, 5100)
    assert store.loops_for("/audio/a.wav") == [
        {"name": "verse", "a": 1100, "b": 5100}]


def test_persists_across_instances(tmp_path):
    path = str(tmp_path / "loops.json")
    LoopStore(path).add("/audio/a.wav", "verse", 1000, 5000)
    assert LoopStore(path).loops_for("/audio/a.wav") == [
        {"name": "verse", "a": 1000, "b": 5000}]


def test_corrupt_file_starts_empty(tmp_path):
    path = tmp_path / "loops.json"
    path.write_text("{not json")
    store = LoopStore(str(path))
    assert store.loops_for("/audio/a.wav") == []
    store.add("/audio/a.wav", "x", 1, 2)  # and can still save
    assert LoopStore(str(path)).loops_for("/audio/a.wav")
