from __future__ import annotations

"""TWW JP ESS R/L hold-before-drop search with a moving slot-4 checkpoint.

Slot 5 is the default state. Each side is first held until a speed drop is seen. The script then reloads the current state,
replays that side only until two frames before the observed drop, switches ESS,
and saves the temp slot on that exact switch frame.
"""

from typing import Optional

from dolphin import controller, event, gui, memory, savestate


CONTROLLER_ID = 0
BASE_STATE_SLOT = 5
TEMP_STATE_SLOT = 4

PLAYER_PTR_ADDR = 0x803BD910
POTENTIAL_SPEED_PTR_ADDR = 0x803AD860
GAME_FRAME_COUNTER_ADDR = 0x803E9D34

OFFSET_CURRENT_ANGLE_Y = 0x206
OFFSET_M34E8_CAMERA_STICK_ANGLE = 0x34E8
OFFSET_POTENTIAL_SPEED = 0x34E4

ESS_RIGHT_X = 146
ESS_LEFT_X = 110
STICK_Y = 128
CSTICK_CENTER_X = 128
CSTICK_Y = 128

SIDE_RIGHT = "right"
SIDE_LEFT = "left"

# This can sometimes drift over time, 26-28 is a good benchmark (26 has the lowest speed decay)
RIGHT_CSTICK_MAGNITUDE = 26
LEFT_CSTICK_MAGNITUDE = 26
SAFETY_FRAMES_BEFORE_DROP = 2
SPEED_DROP_THRESHOLD = 2.0

SHOW_OVERLAY = True
WINDOW_STYLE = """
QWidget {
  background: #171a1f;
  color: #e8f3ff;
  font-family: Consolas, "Cascadia Mono", "Courier New", monospace;
  font-size: 13px;
}
QLabel { color: #b9c7d9; padding: 3px 0; }
QLineEdit {
  background: #101318;
  color: #ffffff;
  border: 1px solid #4e5968;
  border-radius: 4px;
  padding: 5px 7px;
}
QPushButton {
  background: #2d5f9a;
  color: #ffffff;
  border: 0;
  border-radius: 4px;
  padding: 6px 10px;
}
QPushButton:hover { background: #3972b5; }
"""

_window = gui.window("TWW ESS Checkpoint Search", style=WINDOW_STYLE)
_enabled_control = _window.checkbox("Enabled", checked=True)
_right_magnitude_control = _window.input_text("Right ESS C-stick magnitude", "26")
_left_magnitude_control = _window.input_text("Left ESS C-stick magnitude", "26")
_speed_cutoff_control = _window.input_text("Speed-loss cutoff", "2.0")
_base_slot_control = _window.input_text("Base savestate slot", "5")
_temp_slot_control = _window.input_text("Temporary savestate slot", "4")
_start_button = _window.button("Start / restart from base state")
_status_control = _window.text("Set values, then start the search.")


class Readings:
    def __init__(
        self,
        potential_speed: Optional[float],
        current_angle_y: Optional[int],
        m34e8: Optional[int],
    ) -> None:
        self.potential_speed = potential_speed
        self.current_angle_y = current_angle_y
        self.m34e8 = m34e8


class Segment:
    def __init__(self, side: str, frames: int) -> None:
        self.side = side
        self.frames = max(1, int(frames))


PHASE_SEARCH = "search"
PHASE_BUILD_CHECKPOINT = "build_checkpoint"
PHASE_STOPPED = "stopped"

_phase = PHASE_SEARCH
_segments: list[Segment] = []
_candidate_side = SIDE_RIGHT
_candidate_frame = 1
_replay_frame = 1
_has_temp_checkpoint = False

_enabled_cached = False
_enabled_was_checked = False
_session_started = False
_reload_requested = False
_waiting_for_state = False
_reload_slot = BASE_STATE_SLOT
_last_game_frame: Optional[int] = None
_last_speed: Optional[float] = None
_last_readings: Optional[Readings] = None

_drops = 0
_checkpoints = 0
_last_message = "load slot 5 and start right ESS/C+26"


def _parse_int(text: object, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(str(text).strip())
    except Exception:
        return default
    return max(minimum, min(maximum, value))


def _restart_from_base() -> None:
    global BASE_STATE_SLOT, TEMP_STATE_SLOT
    global RIGHT_CSTICK_MAGNITUDE, LEFT_CSTICK_MAGNITUDE, SPEED_DROP_THRESHOLD
    global _phase, _segments, _candidate_side, _candidate_frame, _replay_frame
    global _has_temp_checkpoint, _reload_requested, _waiting_for_state
    global _reload_slot, _session_started
    global _last_game_frame, _last_speed, _last_readings
    global _drops, _checkpoints, _last_message

    BASE_STATE_SLOT = _parse_int(_base_slot_control.value, 5, 0, 99)
    TEMP_STATE_SLOT = _parse_int(_temp_slot_control.value, 4, 0, 99)
    RIGHT_CSTICK_MAGNITUDE = _parse_int(_right_magnitude_control.value, 26, 0, 127)
    LEFT_CSTICK_MAGNITUDE = _parse_int(_left_magnitude_control.value, 26, 0, 127)
    try:
        SPEED_DROP_THRESHOLD = max(1.01, min(2.49, float(str(_speed_cutoff_control.value).strip())))
    except (TypeError, ValueError):
        SPEED_DROP_THRESHOLD = 2.0

    _segments = []
    _phase = PHASE_SEARCH
    _candidate_side = SIDE_RIGHT
    _candidate_frame = 1
    _replay_frame = 1
    _has_temp_checkpoint = False
    _session_started = True
    _reload_requested = True
    _waiting_for_state = True
    _reload_slot = BASE_STATE_SLOT
    _last_game_frame = None
    _last_speed = None
    _last_readings = None
    _drops = 0
    _checkpoints = 0
    _last_message = "restart: load base slot %d, search right ESS/C+%d" % (
        BASE_STATE_SLOT,
        RIGHT_CSTICK_MAGNITUDE,
    )


def _valid_ptr(value: int) -> bool:
    return (0x80000000 <= value < 0x81800000) or (0x90000000 <= value < 0x94000000)


def _read_ptr(address: int) -> Optional[int]:
    try:
        value = int(memory.read_u32(address))
    except Exception:
        return None
    return value if _valid_ptr(value) else None


def _read_u16_ptr(base_address: int, offset: int) -> Optional[int]:
    ptr = _read_ptr(base_address)
    if ptr is None:
        return None
    try:
        return int(memory.read_u16(ptr + offset)) & 0xFFFF
    except Exception:
        return None


def _read_f32_ptr(base_address: int, offset: int) -> Optional[float]:
    ptr = _read_ptr(base_address)
    if ptr is None:
        return None
    try:
        return float(memory.read_f32(ptr + offset))
    except Exception:
        return None


def _read_game_frame() -> Optional[int]:
    try:
        return int(memory.read_u32(GAME_FRAME_COUNTER_ADDR))
    except Exception:
        return None


def _read_all() -> Readings:
    return Readings(
        potential_speed=_read_f32_ptr(POTENTIAL_SPEED_PTR_ADDR, OFFSET_POTENTIAL_SPEED),
        current_angle_y=_read_u16_ptr(PLAYER_PTR_ADDR, OFFSET_CURRENT_ANGLE_Y),
        m34e8=_read_u16_ptr(PLAYER_PTR_ADDR, OFFSET_M34E8_CAMERA_STICK_ANGLE),
    )


def _s16(value: int) -> int:
    value = int(value) & 0xFFFF
    return value - 0x10000 if value >= 0x8000 else value


def _gap(readings: Readings) -> Optional[int]:
    if readings.m34e8 is None or readings.current_angle_y is None:
        return None
    return _s16(readings.m34e8 - readings.current_angle_y)


def _clamp_byte(value: int) -> int:
    return max(0, min(255, int(value)))


def _opposite(side: str) -> str:
    return SIDE_LEFT if side == SIDE_RIGHT else SIDE_RIGHT


def _stick_x(side: str) -> int:
    return ESS_RIGHT_X if side == SIDE_RIGHT else ESS_LEFT_X


def _cstick_signed(side: str) -> int:
    magnitude = RIGHT_CSTICK_MAGNITUDE if side == SIDE_RIGHT else LEFT_CSTICK_MAGNITUDE
    return magnitude if side == SIDE_RIGHT else -magnitude


def _set_sticks(side: str, cstick_signed: Optional[int] = None) -> None:
    if cstick_signed is None:
        cstick_signed = _cstick_signed(side)
    inputs = controller.get_gc_buttons(CONTROLLER_ID)
    inputs["Connected"] = True
    inputs["StickX"] = _stick_x(side)
    inputs["StickY"] = STICK_Y
    inputs["CStickX"] = _clamp_byte(CSTICK_CENTER_X + cstick_signed)
    inputs["CStickY"] = CSTICK_Y
    controller.set_gc_buttons(CONTROLLER_ID, inputs)


def _set_neutral() -> None:
    _set_sticks(SIDE_RIGHT, 0)


def _speed_drop(previous: Optional[float], current: Optional[float]) -> tuple[bool, Optional[float]]:
    if previous is None or current is None:
        return False, None

    # Potential speed is normally negative during a brakeslide, but the same
    # state can be represented with the opposite sign depending on direction
    # and the state setup.  A loss is a reduction in magnitude in either case.
    loss = abs(previous) - abs(current)
    return loss > SPEED_DROP_THRESHOLD, loss


def _active_side() -> str:
    if _phase == PHASE_BUILD_CHECKPOINT and _segments:
        return _segments[-1].side
    return _candidate_side


def _active_local_frame() -> int:
    return _replay_frame if _phase == PHASE_BUILD_CHECKPOINT else _candidate_frame


def _request_load(slot: int, reason: str) -> None:
    global _reload_requested, _reload_slot, _last_message
    _reload_requested = True
    _reload_slot = slot
    _last_message = reason


def _begin_search() -> None:
    global _phase, _candidate_side, _candidate_frame
    global _last_game_frame, _last_speed, _last_readings, _last_message, _waiting_for_state

    _phase = PHASE_SEARCH
    _waiting_for_state = False
    _candidate_side = SIDE_RIGHT if not _segments else _opposite(_segments[-1].side)
    _candidate_frame = 1
    _last_game_frame = None
    _last_speed = None
    _last_readings = None
    _last_message = "SEARCH side=%s C%+d from slot %d" % (
        _candidate_side,
        _cstick_signed(_candidate_side),
        TEMP_STATE_SLOT if _has_temp_checkpoint else BASE_STATE_SLOT,
    )
    _set_sticks(_candidate_side)


def _begin_checkpoint_build() -> None:
    global _phase, _replay_frame, _last_game_frame, _last_speed, _last_readings, _last_message
    global _waiting_for_state

    _phase = PHASE_BUILD_CHECKPOINT
    _waiting_for_state = False
    _replay_frame = 1
    _last_game_frame = None
    _last_speed = None
    _last_readings = None
    segment = _segments[-1]
    _last_message = "REPLAY %s/%df from slot %d, then save slot 4 at swap" % (
        segment.side,
        segment.frames,
        _reload_slot,
    )
    _set_sticks(segment.side)


def _on_drop(speed_delta: Optional[float]) -> None:
    global _drops, _phase, _last_message

    _drops += 1
    safe_frames = max(1, _candidate_frame - SAFETY_FRAMES_BEFORE_DROP)
    _segments.append(Segment(_candidate_side, safe_frames))
    checkpoint_slot = TEMP_STATE_SLOT if _has_temp_checkpoint else BASE_STATE_SLOT
    _phase = PHASE_BUILD_CHECKPOINT
    _last_message = (
        "DROP side=%s local=%d speed_loss=%s; replay %df from slot %d, swap, save slot 4"
        % (
            _candidate_side,
            _candidate_frame,
            "n/a" if speed_delta is None else "%.6f" % speed_delta,
            safe_frames,
            checkpoint_slot,
        )
    )
    _request_load(checkpoint_slot, _last_message)


def _finish_checkpoint(readings: Readings) -> None:
    global _has_temp_checkpoint, _checkpoints, _phase, _candidate_side, _candidate_frame
    global _last_speed, _last_readings, _last_message

    previous = _segments[-1]
    next_side = _opposite(previous.side)

    # This is deliberately after the last verified frame of the old ESS and
    # immediately after submitting the new ESS/C-stick input.
    _set_sticks(next_side)
    savestate.save_to_slot(TEMP_STATE_SLOT)
    _has_temp_checkpoint = True
    _checkpoints += 1
    _phase = PHASE_SEARCH
    _candidate_side = next_side
    _candidate_frame = 1
    _last_speed = readings.potential_speed
    _last_readings = readings
    _last_message = (
        "CHECKPOINT slot=4 saved at %s->%s swap; SEARCH %s/C%+d"
        % (previous.side, next_side, next_side, _cstick_signed(next_side))
    )


def _stop_prefix_failure(readings: Readings, speed_delta: Optional[float]) -> None:
    global _phase, _last_message
    _phase = PHASE_STOPPED
    _last_message = "PREFIX_FAIL replay side=%s local=%d speed_loss=%s gap=%s" % (
        _active_side(),
        _replay_frame,
        "n/a" if speed_delta is None else "%.6f" % speed_delta,
        "n/a" if _gap(readings) is None else str(_gap(readings)),
    )


def _sample_game_frame() -> None:
    global _last_speed, _last_readings, _candidate_frame, _replay_frame

    readings = _read_all()
    failed, speed_delta = _speed_drop(_last_speed, readings.potential_speed)

    if _phase == PHASE_SEARCH:
        if failed:
            _on_drop(speed_delta)
        else:
            _candidate_frame += 1
            _last_speed = readings.potential_speed
            _last_readings = readings
        return

    if _phase == PHASE_BUILD_CHECKPOINT:
        if failed:
            _stop_prefix_failure(readings, speed_delta)
            return
        if _replay_frame >= _segments[-1].frames:
            _finish_checkpoint(readings)
        else:
            _replay_frame += 1
            _last_speed = readings.potential_speed
            _last_readings = readings


def _draw_overlay() -> None:
    if not SHOW_OVERLAY:
        return
    readings = _last_readings
    gui.draw_text(
        (15, 520),
        0xFFFFFFFF,
        (
            "TWW ESS checkpoint hold-before-drop\n"
            "phase=%s  slot5->slot4 checkpoints=%d\n"
            "side=%s C%+d local=%d segments=%d drops=%d\n"
            "speed=%s gap=%s\n"
            "%s"
        )
        % (
            _phase,
            _checkpoints,
            _active_side(),
            _cstick_signed(_active_side()),
            _active_local_frame(),
            len(_segments),
            _drops,
            "n/a" if readings is None or readings.potential_speed is None else "%.6f" % readings.potential_speed,
            "n/a" if readings is None or _gap(readings) is None else str(_gap(readings)),
            _last_message,
        ),
    )


@event.on_hostupdate
def _update_window() -> None:
    global _enabled_cached, _enabled_was_checked, _session_started

    requested_enabled = bool(_enabled_control.checked)
    if _start_button.clicked:
        _restart_from_base()
        try:
            _enabled_control.checked = True
        except (AttributeError, TypeError):
            pass
        requested_enabled = True
    elif requested_enabled and not _enabled_was_checked:
        _restart_from_base()
    elif not requested_enabled:
        _session_started = False

    _enabled_cached = requested_enabled and _session_started
    _enabled_was_checked = requested_enabled

    if not _enabled_cached:
        _status_control.set("Paused. Settings apply when Start / restart is pressed.")
    elif _phase == PHASE_STOPPED:
        _status_control.set(_last_message)
    else:
        _status_control.set(
            "phase=%s  R=%d L=%d  cutoff=%.2f  base=%d temp=%d  checkpoints=%d"
            % (
                _phase,
                RIGHT_CSTICK_MAGNITUDE,
                LEFT_CSTICK_MAGNITUDE,
                SPEED_DROP_THRESHOLD,
                BASE_STATE_SLOT,
                TEMP_STATE_SLOT,
                _checkpoints,
            )
        )

@event.on_frameadvance
def update() -> None:
    global _reload_requested, _waiting_for_state, _last_game_frame, _last_message

    if not _enabled_cached:
        _draw_overlay()
        return

    if _phase == PHASE_STOPPED:
        _set_neutral()
        _draw_overlay()
        return

    if _reload_requested:
        _set_neutral()
        _reload_requested = False
        _waiting_for_state = True
        try:
            savestate.load_from_slot(_reload_slot)
            if _phase == PHASE_BUILD_CHECKPOINT:
                _begin_checkpoint_build()
            else:
                _begin_search()
        except Exception as exc:
            _reload_requested = True
            _last_message = "LOAD_FAILED slot=%d: %s" % (_reload_slot, exc)
        _draw_overlay()
        return

    if _waiting_for_state:
        _set_neutral()
        _draw_overlay()
        return

    _set_sticks(_active_side())
    _draw_overlay()

    game_frame = _read_game_frame()
    if game_frame is None:
        _sample_game_frame()
        _set_sticks(_active_side())
        return

    if _last_game_frame is None:
        _last_game_frame = game_frame
        return

    if game_frame == _last_game_frame:
        return

    _last_game_frame = game_frame
    _sample_game_frame()
    _set_sticks(_active_side())
