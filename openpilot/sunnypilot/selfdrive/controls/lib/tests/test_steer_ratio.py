"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
from types import SimpleNamespace
from unittest import mock

from openpilot.common.parameterized import parameterized
from openpilot.common.test import OpenpilotTestCase
from openpilot.sunnypilot.selfdrive.controls.controlsd_ext import ControlsExt


class TestSteerRatio(OpenpilotTestCase):
  def setUp(self):
    self.controls = mock.create_autospec(ControlsExt, instance=True)
    self.controls.params = mock.MagicMock()

  @parameterized.expand([
    # (use_custom, custom_sr, learned_sr, expected)
    (False, 15.0, 12.5, 12.5),       # Custom disabled: uses learned
    (False, 15.0, 0.05, 0.1),        # Custom disabled: clamps learned to 0.1 min
    (True, None, 12.5, 12.5),        # Custom enabled but None: falls back to learned
    (True, 14.336, 12.5, 14.34),     # Custom enabled: rounded to 2 decimals
    (True, -2.0, 12.5, 0.1),         # Custom enabled: clamped to 0.1 min
    (True, 0.0, 12.5, 0.1),          # Custom enabled: zero clamped to 0.1 min
  ])
  def test_get_steer_ratio(self, use_custom, custom_sr, learned_sr, expected):
    self.controls.params.get_bool.return_value = use_custom
    self.controls.params.get.return_value = custom_sr
    lp = SimpleNamespace(steerRatio=learned_sr)

    sr = ControlsExt.get_steer_ratio(self.controls, lp)
    self.assertEqual(sr, expected)
