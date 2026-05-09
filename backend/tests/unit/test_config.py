import pytest


pytestmark = pytest.mark.unit


def test_default_button_camera_map():
    from app.config import Settings
    s = Settings()
    assert s.button_camera_map == {"1": ["cam1", "cam2"], "2": ["cam3", "cam4"]}


def test_button_camera_map_handles_spaces_and_empties(monkeypatch):
    monkeypatch.setenv("BUTTON1_CAMERAS", " camA , camB , ")
    monkeypatch.setenv("BUTTON2_CAMERAS", "camC")
    from app.config import Settings
    s = Settings()
    assert s.button_camera_map == {"1": ["camA", "camB"], "2": ["camC"]}


def test_segments_and_clips_dir_derived_from_data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from app.config import Settings
    s = Settings()
    assert s.segments_dir == f"{tmp_path}/segments"
    assert s.clips_dir == f"{tmp_path}/clips"


def test_data_dir_trailing_slash_stripped(monkeypatch):
    monkeypatch.setenv("DATA_DIR", "/data/")
    from app.config import Settings
    s = Settings()
    assert s.segments_dir == "/data/segments"
    assert s.clips_dir == "/data/clips"
