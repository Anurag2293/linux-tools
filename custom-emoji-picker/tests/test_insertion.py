from emoji_picker.insertion import (
    TargetWindow,
    parse_geometry,
    parse_window_class,
    paste_accelerator,
    paste_command,
)


def test_terminal_paste_accelerators():
    assert paste_accelerator("terminator") == "ctrl+shift+v"
    assert paste_accelerator("Gnome-terminal") == "ctrl+shift+v"
    assert paste_accelerator("xterm") == "shift+Insert"
    assert paste_accelerator("firefox") == "ctrl+v"


def test_parse_geometry():
    output = "WINDOW=123\nX=-20\nY=40\nWIDTH=1000\nHEIGHT=700\nSCREEN=0\n"
    assert parse_geometry(output) == (-20, 40, 1000, 700)


def test_parse_partial_geometry_defaults_to_zero():
    assert parse_geometry("X=5\ninvalid\n") == (5, 0, 0, 0)


def test_parse_xprop_window_class():
    assert parse_window_class('WM_CLASS(STRING) = "gedit", "Gedit"') == "gedit Gedit"
    assert parse_window_class("WM_CLASS:  not found.") == ""


def test_paste_command_activates_waits_and_pastes():
    target = TargetWindow("1234", "gedit")
    assert paste_command(target, 0.2) == (
        "windowactivate",
        "--sync",
        "1234",
        "sleep",
        "0.200",
        "key",
        "--clearmodifiers",
        "ctrl+v",
    )
