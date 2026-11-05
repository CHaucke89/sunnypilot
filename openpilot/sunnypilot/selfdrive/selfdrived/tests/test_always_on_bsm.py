"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
from openpilot.cereal import messaging, custom
from opendbc.car.structs import car

from openpilot.common.params import Params
from openpilot.common.parameterized import parameterized
from openpilot.common.realtime import DT_CTRL
from openpilot.common.test import OpenpilotTestCase
from openpilot.sunnypilot import PARAMS_UPDATE_PERIOD
from openpilot.sunnypilot.selfdrive.selfdrived.always_on_bsm import AlwaysOnBsm
from openpilot.sunnypilot.selfdrive.selfdrived.events import EventsSP, EVENTS_SP
from openpilot.sunnypilot.selfdrive.selfdrived.events_base import ET

EventNameSP = custom.OnroadEventSP.EventName

# (leftBlindspot, leftBlinker, rightBlindspot, rightBlinker) -> alert expected
BSM_CASES = [
  (False, False, False, False, False),
  (True, False, False, False, False),   # car in left blind spot, no blinker
  (False, True, False, False, False),   # left blinker, left blind spot clear
  (True, True, False, False, True),     # left blinker into occupied left blind spot
  (False, False, True, False, False),   # car in right blind spot, no blinker
  (False, False, False, True, False),   # right blinker, right blind spot clear
  (False, False, True, True, True),     # right blinker into occupied right blind spot
  (True, False, False, True, False),    # left occupied, but signaling right
  (False, True, True, False, False),    # right occupied, but signaling left
  (True, True, True, True, True),
]


def make_cp(enable_bsm: bool = True) -> car.CarParams:
  CP = car.CarParams()
  CP.enableBsm = enable_bsm
  return CP


def make_cs(left_bsm=False, left_blinker=False, right_bsm=False, right_blinker=False) -> car.CarState:
  CS = car.CarState()
  CS.leftBlindspot = left_bsm
  CS.leftBlinker = left_blinker
  CS.rightBlindspot = right_bsm
  CS.rightBlinker = right_blinker
  return CS


def make_sm(lat_active: bool, lateral_state: str = 'torqueState') -> dict:
  msg = messaging.new_message('controlsState')
  state = msg.controlsState.lateralControlState.init(lateral_state)
  state.active = lat_active
  return {'controlsState': msg.controlsState}


class TestAlwaysOnBsm(OpenpilotTestCase):
  def setup_method(self):
    self.params = Params()
    self.params.put_bool("AlwaysOnBsm", True, block=True)
    self.helper = AlwaysOnBsm(make_cp())
    self.events_sp = EventsSP()

  def _update(self, CS, sm) -> bool:
    self.events_sp.clear()
    self.helper.update(CS, sm, self.events_sp)
    return self.events_sp.has(EventNameSP.blindSpotAlert)

  @parameterized.expand(BSM_CASES)
  def test_alert_when_lateral_inactive(self, left_bsm, left_blinker, right_bsm, right_blinker, expected):
    CS = make_cs(left_bsm, left_blinker, right_bsm, right_blinker)
    assert self._update(CS, make_sm(lat_active=False)) == expected

  @parameterized.expand(BSM_CASES)
  def test_no_alert_when_lateral_active(self, left_bsm, left_blinker, right_bsm, right_blinker, _expected):
    # stock lane change flow (laneChangeBlocked) owns the alert while lateral is active
    CS = make_cs(left_bsm, left_blinker, right_bsm, right_blinker)
    assert not self._update(CS, make_sm(lat_active=True))

  @parameterized.expand([('torqueState',), ('pidState',), ('angleState',)])
  def test_lateral_active_across_controllers(self, lateral_state):
    CS = make_cs(left_bsm=True, left_blinker=True)
    assert self._update(CS, make_sm(lat_active=False, lateral_state=lateral_state))
    assert not self._update(CS, make_sm(lat_active=True, lateral_state=lateral_state))

  def test_disabled_by_param(self):
    self.params.put_bool("AlwaysOnBsm", False, block=True)
    helper = AlwaysOnBsm(make_cp())
    self.events_sp.clear()
    helper.update(make_cs(left_bsm=True, left_blinker=True), make_sm(lat_active=False), self.events_sp)
    assert not self.events_sp.has(EventNameSP.blindSpotAlert)

  def test_no_alert_without_bsm_support(self):
    helper = AlwaysOnBsm(make_cp(enable_bsm=False))
    self.events_sp.clear()
    helper.update(make_cs(left_bsm=True, left_blinker=True), make_sm(lat_active=False), self.events_sp)
    assert not self.events_sp.has(EventNameSP.blindSpotAlert)

  def test_param_change_picked_up_periodically(self):
    CS = make_cs(left_bsm=True, left_blinker=True)
    sm = make_sm(lat_active=False)
    assert self._update(CS, sm)  # frame 0: reads param (enabled)

    self.params.put_bool("AlwaysOnBsm", False, block=True)
    period = int(PARAMS_UPDATE_PERIOD / DT_CTRL)

    # still enabled until the next param refresh
    for _ in range(period - 1):
      assert self._update(CS, sm)

    # refresh frame: param re-read, now disabled
    assert not self._update(CS, sm)

  def test_alert_definition(self):
    alerts = EVENTS_SP[EventNameSP.blindSpotAlert]
    assert ET.PERMANENT in alerts
    alert = alerts[ET.PERMANENT]
    assert alert.audible_alert == car.CarControl.HUDControl.AudibleAlert.prompt

  def test_alert_created_when_disengaged(self):
    # PERMANENT alerts must surface while openpilot is disengaged
    self._update(make_cs(right_bsm=True, right_blinker=True), make_sm(lat_active=False))
    alerts = self.events_sp.create_alerts([ET.PERMANENT])
    assert any(a.alert_text_1 in ("Car Detected in Blindspot", "Car in Blindspot") for a in alerts)
