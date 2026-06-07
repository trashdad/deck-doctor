import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from prep_cards import _keep  # noqa: E402


def _base(**over):
    c = {"lang": "en", "layout": "normal",
         "legalities": {"commander": "legal"},
         "set_type": "expansion", "border_color": "black"}
    c.update(over)
    return c


def test_keep_normal_commander_card():
    assert _keep(_base()) is True


def test_drop_acorn_stamp():
    assert _keep(_base(security_stamp="acorn")) is False


def test_drop_silver_border():
    assert _keep(_base(border_color="silver")) is False


def test_drop_funny_set():
    assert _keep(_base(set_type="funny")) is False
