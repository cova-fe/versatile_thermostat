# pylint: disable=line-too-long
""" This file implements the Auto start/stop algorithm as described here:
 https://github.com/jmcollin78/versatile_thermostat/issues/585
"""

import logging
from datetime import datetime
from enum import Enum

from homeassistant.components.climate.const import HVACMode

from .const import (
    AUTO_START_STOP_LEVEL,
    AUTO_START_STOP_ACTION,
)


_LOGGER = logging.getLogger(__name__)

# Some constant to make algorithm depending of level


class DT_MIN(float, Enum):
    NONE = 0  # Not used
    SLOW = 30
    MEDIUM = 15
    FAST = 7


# the measurement cycle (2 min)
CYCLE_SEC = 120

# A temp hysteresis to avoid rapid OFF/ON
TEMP_HYSTERESIS = 0.5


class ERROR_THRESHOLD(float, Enum):
    NONE = 0  # Not used
    SLOW = 10  # 10 cycle above 1° or 5 cycle above 2°, ...
    MEDIUM = 5  # 5 cycle above 1° or 3 cycle above 2°, ..., 1 cycle above 5°
    FAST = 2  # 2 cycle above 1° or 1 cycle above 2°

# ERROR_THRESHOLD = {
#     AUTO_START_STOP_LEVEL_NONE: 0,      # Not used
#     AUTO_START_STOP_LEVEL_SLOW: 10,     # 10 cycle above 1° or 5 cycle above 2°, ...
#     AUTO_START_STOP_LEVEL_MEDIUM: 5,    # 5 cycle above 1° #
#                                         # or 3 cycle above 2°, ..., 1 cycle above 5°
#     AUTO_START_STOP_LEVEL_FAST: 2,      # 2 cycle above 1° or 1 cycle above 2°
# }


class AutoStartStopDetectionAlgorithm:
    """The class that implements the algorithm listed above"""

    _dt: float
    _level: str = AUTO_START_STOP_LEVEL.NONE
    _accumulated_error: float = 0
    _error_threshold: float = ERROR_THRESHOLD.NONE
    _last_calculation_date: datetime | None = None
    _last_switch_date: datetime | None = None

    def __init__(self, level: AUTO_START_STOP_LEVEL, vtherm_name) -> None:
        """Initialize a new algorithm with the right constants"""
        self._vtherm_name = vtherm_name
        self._last_calculation_date = None
        self._last_switch_date = None
        self._init_level(level)

    def _init_level(self, level: AUTO_START_STOP_LEVEL):
        """Initialize a new level"""
        if level == self._level:
            return

        self._level = level
        if self._level != AUTO_START_STOP_LEVEL.NONE:
            self._dt = DT_MIN[AUTO_START_STOP_LEVEL(level).name]
            self._error_threshold = ERROR_THRESHOLD[AUTO_START_STOP_LEVEL(level).name]
            # reset accumulated error if we change the level
            self._accumulated_error = 0

    def calculate_action(  # noqa
        self,
        hvac_mode: HVACMode | None,
        saved_hvac_mode: HVACMode | None,
        target_temp: float,
        current_temp: float,
        slope_min: float,
        now: datetime,
    ) -> AUTO_START_STOP_ACTION:
        """Calculate an eventual action to do depending of the value in parameter"""
        if self._level == AUTO_START_STOP_LEVEL.NONE:
            _LOGGER.debug(
                "%s - auto-start/stop is disabled",
                self,
            )
            return AUTO_START_STOP_ACTION.NONE

        _LOGGER.debug(
            "%s - calculate_action: hvac_mode=%s, saved_hvac_mode=%s, "
            "target_temp=%s, current_temp=%s, slope_min=%s at %s",
            self,
            hvac_mode,
            saved_hvac_mode,
            target_temp,
            current_temp,
            slope_min,
            now,
        )

        if hvac_mode is None or target_temp is None or current_temp is None:
            _LOGGER.debug(
                "%s - Not all mandatory parameters are set. Disable auto-start/stop",
                self,
            )
            return AUTO_START_STOP_ACTION.NONE

        # Calculate the error factor (P)
        error = target_temp - current_temp

        # reduce the error considering the dt between the last measurement
        if self._last_calculation_date is not None:
            dtmin = (now - self._last_calculation_date).total_seconds() / CYCLE_SEC
            # ignore two calls too near (< 24 sec)
            if dtmin <= 0.2:
                _LOGGER.debug(
                    "%s - new calculation of auto_start_stop (%s) "
                    "is too near to the last one (%s). Forget it",
                    self,
                    now,
                    self._last_calculation_date,
                )
                return AUTO_START_STOP_ACTION.NONE
            error = error * dtmin

        # If the error have change its sign, reset smoothly the accumulated error
        if error * self._accumulated_error < 0:
            self._accumulated_error = self._accumulated_error / 2.0

        self._accumulated_error += error

        # Capping of the error
        self._accumulated_error = min(
            self._error_threshold,
            max(-self._error_threshold, self._accumulated_error),
        )

        self._last_calculation_date = now

        temp_at_dt = current_temp + slope_min * self._dt

        # Calculate the number of minute from last_switch
        nb_minutes_since_last_switch = 999
        if self._last_switch_date is not None:
            nb_minutes_since_last_switch = (
                now - self._last_switch_date
            ).total_seconds() / 60

        # Check to turn-off
        # When we hit the threshold, that mean we can turn off
        if hvac_mode == HVACMode.HEAT:
            if (
                self._accumulated_error <= -self._error_threshold
                and temp_at_dt >= target_temp + TEMP_HYSTERESIS
                and nb_minutes_since_last_switch >= self._dt
            ):
                _LOGGER.info(
                    "%s - We need to stop, heating will not be needed for a long time.",
                    self,
                )
                self._last_switch_date = now
                return AUTO_START_STOP_ACTION.OFF
            else:
                _LOGGER.debug("%s - nothing to do, we are heating", self)
                return AUTO_START_STOP_ACTION.NONE

        if hvac_mode == HVACMode.COOL:
            if (
                self._accumulated_error >= self._error_threshold
                and temp_at_dt <= target_temp - TEMP_HYSTERESIS
                and nb_minutes_since_last_switch >= self._dt
            ):
                _LOGGER.info(
                    "%s - We need to stop, cooling will not be needed for a long time.",
                    self,
                )
                self._last_switch_date = now
                return AUTO_START_STOP_ACTION.OFF
            else:
                _LOGGER.debug(
                    "%s - nothing to do, we are cooling",
                    self,
                )
                return AUTO_START_STOP_ACTION.NONE

        # check to turn on
        if hvac_mode == HVACMode.OFF and saved_hvac_mode == HVACMode.HEAT:
            if (
                temp_at_dt <= target_temp - TEMP_HYSTERESIS
                and nb_minutes_since_last_switch >= self._dt
            ):
                _LOGGER.info(
                    "%s - We need to start, because it will be time to heat",
                    self,
                )
                self._last_switch_date = now
                return AUTO_START_STOP_ACTION.ON
            else:
                _LOGGER.debug(
                    "%s - nothing to do, we don't need to heat soon",
                    self,
                )
                return AUTO_START_STOP_ACTION.NONE
        if hvac_mode == HVACMode.OFF and saved_hvac_mode == HVACMode.COOL:
            if (
                temp_at_dt >= target_temp + TEMP_HYSTERESIS
                and nb_minutes_since_last_switch >= self._dt
            ):
                _LOGGER.info(
                    "%s - We need to start, because it will be time to cool",
                    self,
                )
                self._last_switch_date = now
                return AUTO_START_STOP_ACTION.ON
            else:
                _LOGGER.debug(
                    "%s - nothing to do, we don't need to cool soon",
                    self,
                )
                return AUTO_START_STOP_ACTION.NONE

        _LOGGER.debug(
            "%s - nothing to do, no conditions applied",
            self,
        )
        return AUTO_START_STOP_ACTION.NONE

    def set_level(self, level: AUTO_START_STOP_LEVEL):
        """Set a new level"""
        self._init_level(level)

    @property
    def dt_min(self) -> float:
        """Get the dt value"""
        return self._dt

    @property
    def accumulated_error(self) -> float:
        """Get the accumulated error value"""
        return self._accumulated_error

    @property
    def accumulated_error_threshold(self) -> float:
        """Get the accumulated error threshold value"""
        return self._error_threshold

    @property
    def level(self) -> str:
        """Get the level value"""
        return AUTO_START_STOP_LEVEL(self._level).name

    @property
    def last_switch_date(self) -> datetime | None:
        """Get the last of the last switch"""
        return self._last_switch_date

    def __str__(self) -> str:
        return f"AutoStartStopDetectionAlgorithm-{self._vtherm_name}"
