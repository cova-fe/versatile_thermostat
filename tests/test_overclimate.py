# pylint: disable=wildcard-import, unused-wildcard-import, protected-access, unused-argument, line-too-long, too-many-lines

""" Test the Window management """
from unittest.mock import patch, call
from datetime import datetime, timedelta

import logging

from homeassistant.core import HomeAssistant
from homeassistant.components.climate import (
    SERVICE_SET_TEMPERATURE,
)

from custom_components.versatile_thermostat.thermostat_climate import (
    ThermostatOverClimate,
)

from .commons import *

logging.getLogger().setLevel(logging.DEBUG)


@pytest.mark.parametrize("expected_lingering_tasks", [True])
@pytest.mark.parametrize("expected_lingering_timers", [True])
async def test_bug_56(
    hass: HomeAssistant,
    skip_hass_states_is_state,
    skip_turn_on_off_heater,
    skip_send_event,
):
    """Test that in over_climate mode there is no error when underlying climate is not available"""

    the_mock_underlying = MagicMockClimate()
    with patch(
        "custom_components.versatile_thermostat.underlyings.UnderlyingClimate.find_underlying_climate",
        return_value=None,  # dont find the underlying climate
    ):
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="TheOverClimateMockName",
            unique_id="uniqueId",
            data={
                CONF_NAME: "TheOverClimateMockName",
                CONF_THERMOSTAT_TYPE: CONF_THERMOSTAT_CLIMATE,
                CONF_TEMP_SENSOR: "sensor.mock_temp_sensor",
                CONF_EXTERNAL_TEMP_SENSOR: "sensor.mock_ext_temp_sensor",
                CONF_CYCLE_MIN: 5,
                CONF_TEMP_MIN: 15,
                CONF_TEMP_MAX: 30,
                "eco_temp": 17,
                "comfort_temp": 18,
                "boost_temp": 19,
                CONF_USE_WINDOW_FEATURE: False,
                CONF_USE_MOTION_FEATURE: False,
                CONF_USE_POWER_FEATURE: False,
                CONF_USE_PRESENCE_FEATURE: False,
                CONF_CLIMATE: "climate.mock_climate",
                CONF_MINIMAL_ACTIVATION_DELAY: 30,
                CONF_SECURITY_DELAY_MIN: 5,
                CONF_SECURITY_MIN_ON_PERCENT: 0.3,
            },
        )

        entity: BaseThermostat = await create_thermostat(
            hass, entry, "climate.theoverclimatemockname"
        )
        assert entity
        # cause the underlying climate was not found
        assert entity.is_over_climate is True
        assert entity.underlying_entity(0)._underlying_climate is None

        # Should not failed
        entity.update_custom_attributes()

        # try to call async_control_heating
        try:
            ret = await entity.async_control_heating()
            # an exception should be send
            assert ret is False
        except Exception:  # pylint: disable=broad-exception-caught
            assert False

    # This time the underlying will be found
    with patch(
        "custom_components.versatile_thermostat.underlyings.UnderlyingClimate.find_underlying_climate",
        return_value=the_mock_underlying,  # dont find the underlying climate
    ):
        # try to call async_control_heating
        try:
            await entity.async_control_heating()
        except UnknownEntity:
            assert False
        except Exception:  # pylint: disable=broad-exception-caught
            assert False

        # Should not failed
        entity.update_custom_attributes()


@pytest.mark.parametrize("expected_lingering_tasks", [True])
@pytest.mark.parametrize("expected_lingering_timers", [True])
async def test_bug_82(
    hass: HomeAssistant,
    skip_hass_states_is_state,
    skip_turn_on_off_heater,
    skip_send_event,
):
    """Test that when a underlying climate is not available the VTherm doesn't go into safety mode"""

    tz = get_tz(hass)  # pylint: disable=invalid-name
    now: datetime = datetime.now(tz=tz)

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="TheOverClimateMockName",
        unique_id="uniqueId",
        data=PARTIAL_CLIMATE_CONFIG,  # 5 minutes security delay
    )

    fake_underlying_climate = MockUnavailableClimate(
        hass, "mockUniqueId", "MockClimateName", {}
    )

    with patch(
        "custom_components.versatile_thermostat.base_thermostat.BaseThermostat.send_event"
    ) as mock_send_event, patch(
        "custom_components.versatile_thermostat.underlyings.UnderlyingClimate.find_underlying_climate",
        return_value=fake_underlying_climate,
    ) as mock_find_climate:
        entity = await create_thermostat(hass, entry, "climate.theoverclimatemockname")

        assert entity

        assert entity.name == "TheOverClimateMockName"
        assert entity.is_over_climate is True
        # assert entity.hvac_action is HVACAction.OFF
        assert entity.hvac_mode is HVACMode.OFF
        # assert entity.hvac_mode is None
        assert entity.target_temperature == entity.min_temp
        assert entity.preset_modes == [
            PRESET_NONE,
            PRESET_FROST_PROTECTION,
            PRESET_ECO,
            PRESET_COMFORT,
            PRESET_BOOST,
        ]
        assert entity.preset_mode is PRESET_NONE
        assert entity._security_state is False

        # should have been called with EventType.PRESET_EVENT and EventType.HVAC_MODE_EVENT
        assert mock_send_event.call_count == 2
        mock_send_event.assert_has_calls(
            [
                call.send_event(EventType.PRESET_EVENT, {"preset": PRESET_NONE}),
                call.send_event(
                    EventType.HVAC_MODE_EVENT,
                    {"hvac_mode": HVACMode.OFF},
                ),
            ]
        )

        assert mock_find_climate.call_count == 1
        assert mock_find_climate.mock_calls[0] == call()
        mock_find_climate.assert_has_calls([call.find_underlying_entity()])

        # Force safety mode
        assert entity._last_ext_temperature_measure is not None
        assert entity._last_temperature_measure is not None
        assert (
            entity._last_temperature_measure.astimezone(tz) - now
        ).total_seconds() < 1
        assert (
            entity._last_ext_temperature_measure.astimezone(tz) - now
        ).total_seconds() < 1

        # Tries to turns on the Thermostat
        await entity.async_set_hvac_mode(HVACMode.HEAT)
        assert entity.hvac_mode == HVACMode.HEAT

        # 2. activate security feature when date is expired
        with patch(
            "custom_components.versatile_thermostat.base_thermostat.BaseThermostat.send_event"
        ) as mock_send_event, patch(
            "custom_components.versatile_thermostat.underlyings.UnderlyingSwitch.turn_on"
        ):
            event_timestamp = now - timedelta(minutes=6)

            # set temperature to 15 so that on_percent will be > security_min_on_percent (0.2)
            await send_temperature_change_event(entity, 15, event_timestamp)
            # Should stay False
            assert entity.security_state is False
            assert entity.preset_mode == "none"
            assert entity._saved_preset_mode == "none"


@pytest.mark.parametrize("expected_lingering_tasks", [True])
@pytest.mark.parametrize("expected_lingering_timers", [True])
async def test_bug_101(
    hass: HomeAssistant,
    skip_hass_states_is_state,
    skip_turn_on_off_heater,
    skip_send_event,
):
    """Test that when a underlying climate target temp is changed, the VTherm change its own temperature target and switch to manual"""

    tz = get_tz(hass)  # pylint: disable=invalid-name
    now: datetime = datetime.now(tz=tz)

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="TheOverClimateMockName",
        unique_id="uniqueId",
        data=PARTIAL_CLIMATE_NOT_REGULATED_CONFIG,  # 5 minutes security delay
    )

    # Underlying is in HEAT mode but should be shutdown at startup
    fake_underlying_climate = MockClimate(
        hass, "mockUniqueId", "MockClimateName", {}, HVACMode.HEAT, HVACAction.HEATING
    )

    with patch(
        "custom_components.versatile_thermostat.base_thermostat.BaseThermostat.send_event"
    ) as mock_send_event, patch(
        "custom_components.versatile_thermostat.underlyings.UnderlyingClimate.find_underlying_climate",
        return_value=fake_underlying_climate,
    ) as mock_find_climate, patch(
        "custom_components.versatile_thermostat.underlyings.UnderlyingClimate.set_hvac_mode"
    ) as mock_underlying_set_hvac_mode:
        entity = await create_thermostat(hass, entry, "climate.theoverclimatemockname")

        assert entity

        assert entity.name == "TheOverClimateMockName"
        assert entity.is_over_climate is True
        assert entity.hvac_mode is HVACMode.OFF
        # because in MockClimate HVACAction is HEATING if hvac_mode is not set
        assert entity.hvac_action is HVACAction.HEATING
        # Underlying should have been shutdown
        assert mock_underlying_set_hvac_mode.call_count == 1
        mock_underlying_set_hvac_mode.assert_has_calls(
            [
                call.set_hvac_mode(HVACMode.OFF),
            ]
        )

        assert entity.target_temperature == entity.min_temp
        assert entity.preset_mode is PRESET_NONE

        # should have been called with EventType.PRESET_EVENT and EventType.HVAC_MODE_EVENT
        assert mock_send_event.call_count == 2
        mock_send_event.assert_has_calls(
            [
                call.send_event(EventType.PRESET_EVENT, {"preset": PRESET_NONE}),
                call.send_event(
                    EventType.HVAC_MODE_EVENT,
                    {"hvac_mode": HVACMode.OFF},
                ),
            ]
        )

        assert mock_find_climate.call_count == 1
        assert mock_find_climate.mock_calls[0] == call()
        mock_find_climate.assert_has_calls([call.find_underlying_entity()])

        # 1. Force preset mode
        await entity.async_set_hvac_mode(HVACMode.HEAT)
        assert entity.hvac_mode == HVACMode.HEAT
        await entity.async_set_preset_mode(PRESET_COMFORT)
        assert entity.preset_mode == PRESET_COMFORT

        # 2. Change the target temp of underlying thermostat at now -> the event will be disgarded because to fast (to avoid loop cf issue 121)
        await send_climate_change_event_with_temperature(
            entity,
            HVACMode.HEAT,
            HVACMode.HEAT,
            HVACAction.OFF,
            HVACAction.OFF,
            now,
            12.75,
            True,
            "climate.mock_climate",  # the underlying climate entity id
        )
        # Should NOT have been switched to Manual preset
        assert entity.target_temperature == 17
        assert entity.preset_mode is PRESET_COMFORT

        # 3. Change the target temp of underlying thermostat at 11 sec later -> the event will be taken
        # Wait 11 sec
        event_timestamp = now + timedelta(seconds=11)
        assert entity.is_regulated is False
        await send_climate_change_event_with_temperature(
            entity,
            HVACMode.HEAT,
            HVACMode.HEAT,
            HVACAction.OFF,
            HVACAction.OFF,
            event_timestamp,
            12.75,
            True,
            "climate.mock_climate",  # the underlying climate entity id
        )
        assert entity.target_temperature == 12.75
        assert entity.preset_mode is PRESET_NONE


@pytest.mark.parametrize("expected_lingering_timers", [True])
async def test_bug_508(
    hass: HomeAssistant,
    skip_hass_states_is_state,
    skip_turn_on_off_heater,
    skip_send_event,
):
    """Test that it not possible to set the target temperature under the min_temp setting"""

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="TheOverClimateMockName",
        unique_id="uniqueId",
        # default value are min 15°, max 31°, step 0.1
        data=PARTIAL_CLIMATE_CONFIG,  # 5 minutes security delay
    )

    # Min_temp is 10 and max_temp is 31 and features contains TARGET_TEMPERATURE_RANGE
    fake_underlying_climate = MagicMockClimateWithTemperatureRange()

    with patch(
        "custom_components.versatile_thermostat.base_thermostat.BaseThermostat.send_event"
    ), patch(
        "custom_components.versatile_thermostat.underlyings.UnderlyingClimate.find_underlying_climate",
        return_value=fake_underlying_climate,
    ), patch(
        "homeassistant.core.ServiceRegistry.async_call"
    ) as mock_service_call:
        entity = await create_thermostat(hass, entry, "climate.theoverclimatemockname")

        assert entity

        assert entity.name == "TheOverClimateMockName"
        assert entity.is_over_climate is True
        assert entity.hvac_mode is HVACMode.OFF
        # The VTherm value and not the underlying value
        assert entity.target_temperature_step == 0.1
        assert entity.target_temperature == entity.min_temp
        assert entity.is_regulated is True

        assert mock_service_call.call_count == 0

        # Set the hvac_mode to HEAT
        await entity.async_set_hvac_mode(HVACMode.HEAT)

        # Not In the accepted interval -> should be converted into 10 (the min) and send with target_temp_high and target_temp_low
        await entity.async_set_temperature(temperature=8.5)

        # MagicMock climate is already HEAT by default. So there is no SET_HAVC_MODE call
        assert mock_service_call.call_count == 1
        mock_service_call.assert_has_calls(
            [
                call.async_call(
                    "climate",
                    SERVICE_SET_TEMPERATURE,
                    {
                        "entity_id": "climate.mock_climate",
                        # "temperature": 17.5,
                        "target_temp_high": 10,
                        "target_temp_low": 10,
                        "temperature": 10,
                    },
                ),
            ]
        )

    with patch("homeassistant.core.ServiceRegistry.async_call") as mock_service_call:
        # Not In the accepted interval -> should be converted into 10 (the min) and send with target_temp_high and target_temp_low
        await entity.async_set_temperature(temperature=32)

        # MagicMock climate is already HEAT by default. So there is no SET_HAVC_MODE call
        assert mock_service_call.call_count == 1
        mock_service_call.assert_has_calls(
            [
                call.async_call(
                    "climate",
                    SERVICE_SET_TEMPERATURE,
                    {
                        "entity_id": "climate.mock_climate",
                        "target_temp_high": 31,
                        "target_temp_low": 31,
                        "temperature": 31,
                    },
                ),
            ]
        )


@pytest.mark.parametrize("expected_lingering_tasks", [True])
@pytest.mark.parametrize("expected_lingering_timers", [True])
async def test_bug_524(hass: HomeAssistant, skip_hass_states_is_state):
    """Test when switching from Cool to Heat the new temperature in Heat mode should be used"""

    # vtherm_api: VersatileThermostatAPI = VersatileThermostatAPI.get_vtherm_api(hass)

    # The temperatures to set
    temps = {
        "frost": 7.0,
        "eco": 17.0,
        "comfort": 19.0,
        "boost": 21.0,
        "eco_ac": 27.0,
        "comfort_ac": 25.0,
        "boost_ac": 23.0,
        "frost_away": 7.1,
        "eco_away": 17.1,
        "comfort_away": 19.1,
        "boost_away": 21.1,
        "eco_ac_away": 27.1,
        "comfort_ac_away": 25.1,
        "boost_ac_away": 23.1,
    }

    config_entry = MockConfigEntry(
        domain=DOMAIN,
        title="TheOverClimateMockName",
        unique_id="overClimateUniqueId",
        data={
            CONF_NAME: "overClimate",
            CONF_TEMP_SENSOR: "sensor.mock_temp_sensor",
            CONF_THERMOSTAT_TYPE: CONF_THERMOSTAT_CLIMATE,
            CONF_EXTERNAL_TEMP_SENSOR: "sensor.mock_ext_temp_sensor",
            CONF_CYCLE_MIN: 5,
            CONF_TEMP_MIN: 15,
            CONF_TEMP_MAX: 30,
            CONF_USE_WINDOW_FEATURE: False,
            CONF_USE_MOTION_FEATURE: False,
            CONF_USE_POWER_FEATURE: False,
            CONF_USE_PRESENCE_FEATURE: True,
            CONF_PRESENCE_SENSOR: "binary_sensor.presence_sensor",
            CONF_CLIMATE: "climate.mock_climate",
            CONF_MINIMAL_ACTIVATION_DELAY: 30,
            CONF_SECURITY_DELAY_MIN: 5,
            CONF_SECURITY_MIN_ON_PERCENT: 0.3,
            CONF_AUTO_FAN_MODE: CONF_AUTO_FAN_TURBO,
            CONF_AC_MODE: True,
        },
        # | temps,
    )

    fake_underlying_climate = MockClimate(
        hass=hass,
        unique_id="mock_climate",
        name="mock_climate",
        hvac_modes=[HVACMode.OFF, HVACMode.COOL, HVACMode.HEAT, HVACMode.FAN_ONLY],
    )

    with patch(
        "custom_components.versatile_thermostat.underlyings.UnderlyingClimate.find_underlying_climate",
        return_value=fake_underlying_climate,
    ):
        vtherm: ThermostatOverClimate = await create_thermostat(
            hass, config_entry, "climate.overclimate"
        )

    assert vtherm is not None

    # We search for NumberEntities
    for preset_name, value in temps.items():

        await set_climate_preset_temp(vtherm, preset_name, value)

        temp_entity: NumberEntity = search_entity(
            hass,
            "number.overclimate_preset_" + preset_name + PRESET_TEMP_SUFFIX,
            NUMBER_DOMAIN,
        )
        assert temp_entity
        # Because set_value is not implemented in Number class (really don't understand why...)
        assert temp_entity.state == value

    # 1. Set mode to Heat and preset to Comfort
    await send_presence_change_event(vtherm, True, False, datetime.now())
    await vtherm.async_set_hvac_mode(HVACMode.HEAT)
    await vtherm.async_set_preset_mode(PRESET_COMFORT)
    await hass.async_block_till_done()

    assert vtherm.target_temperature == 19.0

    # 2. Only change the HVAC_MODE (and keep preset to comfort)
    await vtherm.async_set_hvac_mode(HVACMode.COOL)
    await hass.async_block_till_done()
    assert vtherm.target_temperature == 25.0

    # 3. Only change the HVAC_MODE (and keep preset to comfort)
    await vtherm.async_set_hvac_mode(HVACMode.HEAT)
    await hass.async_block_till_done()
    assert vtherm.target_temperature == 19.0

    # 4. Change presence to off
    await send_presence_change_event(vtherm, False, True, datetime.now())
    await hass.async_block_till_done()
    assert vtherm.target_temperature == 19.1

    # 5. Change hvac_mode to AC
    await vtherm.async_set_hvac_mode(HVACMode.COOL)
    await hass.async_block_till_done()
    assert vtherm.target_temperature == 25.1

    # 6. Change presence to on
    await send_presence_change_event(vtherm, True, False, datetime.now())
    await hass.async_block_till_done()
    assert vtherm.target_temperature == 25