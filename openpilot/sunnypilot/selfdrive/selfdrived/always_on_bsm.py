"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
from openpilot.cereal import messaging, custom
from opendbc.car.structs import car

from openpilot.common.params import Params
from openpilot.common.realtime import DT_CTRL
from openpilot.sunnypilot import PARAMS_UPDATE_PERIOD
from openpilot.sunnypilot.selfdrive.selfdrived.events import EventsSP

EventNameSP = custom.OnroadEventSP.EventName


class AlwaysOnBsm:
  """
  Always-On Blind Spot Monitoring: raise an audible blind spot alert when a vehicle
  is detected on the signaled side, even while lateral control is inactive.
  When lateral is active, the stock lane change flow (laneChangeBlocked) handles it.
  """
  def __init__(self, CP: car.CarParams):
    self._params = Params()
    self._available = CP.enableBsm
    self.frame = -1
    self.enabled = self._params.get_bool("AlwaysOnBsm")

  def _read_params(self) -> None:
    if self.frame % int(PARAMS_UPDATE_PERIOD / DT_CTRL) == 0:
      self.enabled = self._params.get_bool("AlwaysOnBsm")

  @staticmethod
  def _lateral_active(sm: messaging.SubMaster) -> bool:
    lateral_control_state = sm['controlsState'].lateralControlState
    return bool(getattr(lateral_control_state, lateral_control_state.which()).active)

  def update(self, CS: car.CarState, sm: messaging.SubMaster, events_sp: EventsSP) -> None:
    self.frame += 1
    self._read_params()

    if not (self._available and self.enabled) or self._lateral_active(sm):
      return

    if (CS.leftBlindspot and CS.leftBlinker) or (CS.rightBlindspot and CS.rightBlinker):
      events_sp.add(EventNameSP.blindSpotAlert)
