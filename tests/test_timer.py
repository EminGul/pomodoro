from pomodoro.timer import SessionType, TimerState

W, SB, LB = 25 * 60, 5 * 60, 15 * 60  # seconds


def make_state(work_secs: int = W, spb: int = 4) -> TimerState:
    return TimerState.initial(work_secs=work_secs, sessions_before_long_break=spb)


def test_initial_state():
    state = make_state()
    assert state.session_type == SessionType.WORK
    assert state.seconds_remaining == W
    assert state.work_session_count == 0
    assert state.total_work_sessions == 0


def test_tick_decrements():
    state = make_state()
    ended = state.tick()
    assert not ended
    assert state.seconds_remaining == W - 1


def test_tick_signals_end_at_zero():
    state = make_state(work_secs=2)
    assert not state.tick()
    assert state.tick()


def test_work_advances_to_short_break():
    state = make_state()
    state.advance(W, SB, LB)
    assert state.session_type == SessionType.SHORT_BREAK
    assert state.seconds_remaining == SB


def test_short_break_advances_to_work():
    state = make_state()
    state.advance(W, SB, LB)
    state.advance(W, SB, LB)
    assert state.session_type == SessionType.WORK


def test_long_break_after_four_sessions():
    state = make_state(spb=4)
    for _ in range(3):
        state.advance(W, SB, LB)
        state.advance(W, SB, LB)
    state.advance(W, SB, LB)
    assert state.session_type == SessionType.LONG_BREAK
    assert state.seconds_remaining == LB


def test_work_session_count_resets_after_long_break():
    state = make_state(spb=4)
    for _ in range(4):
        state.advance(W, SB, LB)
        if state.session_type != SessionType.WORK:
            state.advance(W, SB, LB)
    assert state.work_session_count == 0


def test_total_work_sessions_accumulates():
    state = make_state(spb=4)
    for _ in range(4):
        state.advance(W, SB, LB)
        if state.session_type != SessionType.WORK:
            state.advance(W, SB, LB)
    assert state.total_work_sessions == 4


def test_custom_sessions_before_long_break():
    state = make_state(spb=2)
    state.advance(W, SB, LB)
    state.advance(W, SB, LB)
    state.advance(W, SB, LB)
    assert state.session_type == SessionType.LONG_BREAK


def test_long_break_to_work():
    state = make_state(spb=1)
    state.advance(W, SB, LB)
    state.advance(W, SB, LB)
    assert state.session_type == SessionType.WORK


def test_test_preset_durations_are_seconds_not_minutes():
    # 10s work should expire after 10 ticks, not 600
    state = make_state(work_secs=10, spb=4)
    for _ in range(9):
        assert not state.tick()
    assert state.tick()
