# pylint: disable=protected-access, unused-argument, line-too-long
""" Test the Central Power management """
from unittest.mock import patch, AsyncMock, MagicMock, PropertyMock
from datetime import datetime, timedelta
import logging

from custom_components.versatile_thermostat.feature_power_manager import (
    FeaturePowerManager,
)
from custom_components.versatile_thermostat.central_feature_power_manager import (
    CentralFeaturePowerManager,
)
from .commons import *  # pylint: disable=wildcard-import, unused-wildcard-import

logging.getLogger().setLevel(logging.DEBUG)


@pytest.mark.parametrize(
    "use_power_feature, power_entity_id, max_power_entity_id, power_temp, is_configured",
    [
        (True, "sensor.power_id", "sensor.max_power_id", 13, True),
        (True, None, "sensor.max_power_id", 13, False),
        (True, "sensor.power_id", None, 13, False),
        (True, "sensor.power_id", "sensor.max_power_id", None, False),
        (False, "sensor.power_id", "sensor.max_power_id", 13, False),
    ],
)
async def test_central_power_manager_init(
    hass: HomeAssistant,
    use_power_feature,
    power_entity_id,
    max_power_entity_id,
    power_temp,
    is_configured,
):
    """Test creation and post_init of the Central Power Manager"""
    vtherm_api: VersatileThermostatAPI = MagicMock(spec=VersatileThermostatAPI)
    central_power_manager = CentralFeaturePowerManager(hass, vtherm_api)

    assert central_power_manager.is_configured is False
    assert central_power_manager.current_max_power is None
    assert central_power_manager.current_power is None
    assert central_power_manager.power_temperature is None
    assert central_power_manager.name == "centralPowerManager"

    # 2. post_init
    central_power_manager.post_init(
        {
            CONF_POWER_SENSOR: power_entity_id,
            CONF_MAX_POWER_SENSOR: max_power_entity_id,
            CONF_USE_POWER_FEATURE: use_power_feature,
            CONF_PRESET_POWER: power_temp,
        }
    )

    assert central_power_manager.is_configured == is_configured
    assert central_power_manager.current_max_power is None
    assert central_power_manager.current_power is None
    assert central_power_manager.power_temperature == power_temp

    # 3. start listening
    await central_power_manager.start_listening()
    assert len(central_power_manager._active_listener) == (2 if is_configured else 0)

    # 4. stop listening
    central_power_manager.stop_listening()
    assert len(central_power_manager._active_listener) == 0


@pytest.mark.parametrize(
    "vtherm_configs, results",
    [
        # simple sort
        (
            [
                {
                    "name": "vtherm1",
                    "is_configured": True,
                    "is_on": True,
                    "current_temperature": 13,
                    "target_temperature": 12,
                    "saved_target_temp": 18,
                    "is_overpowering_detected": False,
                },
                {
                    "name": "vtherm2",
                    "is_configured": True,
                    "is_on": True,
                    "current_temperature": 18,
                    "target_temperature": 12,
                    "saved_target_temp": 18,
                    "is_overpowering_detected": False,
                },
                {
                    "name": "vtherm3",
                    "is_configured": True,
                    "is_on": True,
                    "current_temperature": 12,
                    "target_temperature": 18,
                    "saved_target_temp": 18,
                    "is_overpowering_detected": False,
                },
            ],
            ["vtherm2", "vtherm1", "vtherm3"],
        ),
        # Ignore power not configured and not on
        (
            [
                {
                    "name": "vtherm1",
                    "is_configured": False,
                    "is_on": True,
                    "current_temperature": 13,
                    "target_temperature": 12,
                    "saved_target_temp": 18,
                    "is_overpowering_detected": False,
                },
                {
                    "name": "vtherm2",
                    "is_configured": True,
                    "is_on": False,
                    "current_temperature": 18,
                    "target_temperature": 12,
                    "saved_target_temp": 18,
                    "is_overpowering_detected": False,
                },
                {
                    "name": "vtherm3",
                    "is_configured": True,
                    "is_on": True,
                    "current_temperature": 12,
                    "target_temperature": 18,
                    "saved_target_temp": 18,
                    "is_overpowering_detected": False,
                },
            ],
            ["vtherm3"],
        ),
        # None current_temperature are in last
        (
            [
                {
                    "name": "vtherm1",
                    "is_configured": True,
                    "is_on": True,
                    "current_temperature": 13,
                    "target_temperature": 12,
                    "saved_target_temp": 18,
                    "is_overpowering_detected": False,
                },
                {
                    "name": "vtherm2",
                    "is_configured": True,
                    "is_on": True,
                    "current_temperature": None,
                    "target_temperature": 12,
                    "saved_target_temp": 18,
                    "is_overpowering_detected": False,
                },
                {
                    "name": "vtherm3",
                    "is_configured": True,
                    "is_on": True,
                    "current_temperature": 12,
                    "target_temperature": 18,
                    "saved_target_temp": 18,
                    "is_overpowering_detected": False,
                },
            ],
            ["vtherm1", "vtherm3", "vtherm2"],
        ),
        # None target_temperature are in last
        (
            [
                {
                    "name": "vtherm1",
                    "is_configured": True,
                    "is_on": True,
                    "current_temperature": 13,
                    "target_temperature": 12,
                    "saved_target_temp": 18,
                    "is_overpowering_detected": False,
                },
                {
                    "name": "vtherm2",
                    "is_configured": True,
                    "is_on": True,
                    "current_temperature": 18,
                    "target_temperature": None,
                    "saved_target_temp": 18,
                    "is_overpowering_detected": False,
                },
                {
                    "name": "vtherm3",
                    "is_configured": True,
                    "is_on": True,
                    "current_temperature": 12,
                    "target_temperature": 18,
                    "saved_target_temp": 18,
                    "is_overpowering_detected": False,
                },
            ],
            ["vtherm1", "vtherm3", "vtherm2"],
        ),
        # simple sort with overpowering detected
        (
            [
                {
                    "name": "vtherm1",
                    "is_configured": True,
                    "is_on": True,
                    "current_temperature": 13,
                    # "target_temperature": 12,
                    "saved_target_temp": 21,
                    "is_overpowering_detected": True,
                },
                {
                    "name": "vtherm2",
                    "is_configured": True,
                    "is_on": True,
                    "current_temperature": 18,
                    # "target_temperature": 12,
                    "saved_target_temp": 17,
                    "is_overpowering_detected": True,
                },
                {
                    "name": "vtherm3",
                    "is_configured": True,
                    "is_on": True,
                    "current_temperature": 12,
                    # "target_temperature": 18,
                    "saved_target_temp": 16,
                    "is_overpowering_detected": True,
                },
            ],
            ["vtherm2", "vtherm3", "vtherm1"],
        ),
    ],
)
async def test_central_power_manageer_find_vtherms(
    hass: HomeAssistant, vtherm_configs, results
):
    """Test the find_all_vtherm_with_power_management_sorted_by_dtemp"""
    vtherm_api: VersatileThermostatAPI = MagicMock(spec=VersatileThermostatAPI)
    central_power_manager = CentralFeaturePowerManager(hass, vtherm_api)

    vtherms = []
    for vtherm_config in vtherm_configs:
        vtherm = MagicMock(spec=BaseThermostat)
        vtherm.name = vtherm_config.get("name")
        vtherm.is_on = vtherm_config.get("is_on")
        vtherm.current_temperature = vtherm_config.get("current_temperature")
        vtherm.target_temperature = vtherm_config.get("target_temperature")
        vtherm.saved_target_temp = vtherm_config.get("saved_target_temp")
        vtherm.power_manager.is_configured = vtherm_config.get("is_configured")
        vtherm.power_manager.is_overpowering_detected = vtherm_config.get("is_overpowering_detected")
        vtherms.append(vtherm)

    with patch(
        "custom_components.versatile_thermostat.central_feature_power_manager.CentralFeaturePowerManager.get_climate_components_entities",
        return_value=vtherms,
    ):
        vtherm_sorted = (
            central_power_manager.find_all_vtherm_with_power_management_sorted_by_dtemp()
        )

        # extract results
        vtherm_results = [vtherm.name for vtherm in vtherm_sorted]

        assert vtherm_results == results


@pytest.mark.parametrize(
    "current_power, current_max_power, vtherm_configs, expected_results",
    [
        # simple nominal test (initialize overpowering state in VTherm)
        (
            1000,
            5000,
            [
                {
                    "name": "vtherm1",
                    "device_power": 100,
                    "is_device_active": False,
                    "is_over_climate": False,
                    "nb_underlying_entities": 1,
                    "on_percent": 0,
                    "is_overpowering_detected": False,
                    "overpowering_state": STATE_UNKNOWN,
                },
                {
                    "name": "vtherm2",
                    "device_power": 10000,
                    "is_device_active": True,
                    "is_over_climate": False,
                    "nb_underlying_entities": 4,
                    "on_percent": 100,
                    "is_overpowering_detected": False,
                    "overpowering_state": STATE_UNKNOWN,
                },
                {
                    "name": "vtherm3",
                    "device_power": 5000,
                    "is_device_active": True,
                    "is_over_climate": True,
                    "is_overpowering_detected": False,
                    "overpowering_state": STATE_UNKNOWN,
                },
                {"name": "vtherm4", "device_power": 1000, "is_device_active": True, "is_over_climate": True, "is_overpowering_detected": False, "overpowering_state": STATE_OFF},
            ],
            # init vtherm1 to False
            {"vtherm3": False, "vtherm2": False, "vtherm1": False},
        ),
        # Un-shedding only (will be taken in reverse order)
        (
            1000,
            2000,
            [
                # should be not unshedded (too much power will be added)
                {
                    "name": "vtherm1",
                    "device_power": 800,
                    "is_device_active": False,
                    "is_over_climate": False,
                    "nb_underlying_entities": 1,
                    "on_percent": 1,
                    "is_overpowering_detected": True,
                    "overpowering_state": STATE_ON,
                },
                # already stay unshedded cause already unshedded
                {
                    "name": "vtherm2",
                    "device_power": 100,
                    "is_device_active": True,
                    "is_over_climate": True,
                    "is_overpowering_detected": False,
                    "overpowering_state": STATE_OFF,
                },
                # should be unshedded
                {
                    "name": "vtherm3",
                    "device_power": 200,
                    "is_device_active": False,
                    "is_over_climate": True,
                    "is_overpowering_detected": True,
                    "overpowering_state": STATE_ON,
                },
                # should be unshedded
                {
                    "name": "vtherm4",
                    "device_power": 300,
                    "is_device_active": False,
                    "is_over_climate": False,
                    "nb_underlying_entities": 1,
                    "on_percent": 1,
                    "is_overpowering_detected": True,
                    "overpowering_state": STATE_ON,
                },
            ],
            {"vtherm4": False, "vtherm3": False},
        ),
        # Shedding
        (
            2000,
            1000,
            [
                # should be overpowering
                {
                    "name": "vtherm1",
                    "device_power": 300,
                    "is_device_active": True,
                    "is_over_climate": False,
                    "nb_underlying_entities": 1,
                    "on_percent": 1,
                    "is_overpowering_detected": False,
                    "overpowering_state": STATE_OFF,
                },
                # should be overpowering with many underlmying entities
                {
                    "name": "vtherm2",
                    "device_power": 400,
                    "is_device_active": True,
                    "is_over_climate": False,
                    "nb_underlying_entities": 4,
                    "on_percent": 0.1,
                    "is_overpowering_detected": False,
                    "overpowering_state": STATE_UNKNOWN,
                },
                # over_climate should be overpowering
                {
                    "name": "vtherm3",
                    "device_power": 100,
                    "is_device_active": True,
                    "is_over_climate": True,
                    "is_overpowering_detected": False,
                    "overpowering_state": STATE_OFF,
                },
                # should pass cause not active
                {
                    "name": "vtherm4",
                    "device_power": 800,
                    "is_device_active": False,
                    "is_over_climate": False,
                    "nb_underlying_entities": 1,
                    "on_percent": 1,
                    "is_overpowering_detected": False,
                },
                # should be not overpowering (already overpowering)
                {
                    "name": "vtherm5",
                    "device_power": 400,
                    "is_device_active": True,
                    "is_over_climate": False,
                    "nb_underlying_entities": 4,
                    "on_percent": 0.1,
                    "is_overpowering_detected": True,
                    "overpowering_state": STATE_ON,
                },
                # should be overpowering with many underluying entities
                {
                    "name": "vtherm6",
                    "device_power": 400,
                    "is_device_active": True,
                    "is_over_climate": False,
                    "nb_underlying_entities": 4,
                    "on_percent": 0.1,
                    "is_overpowering_detected": False,
                    "overpowering_state": STATE_UNKNOWN,
                },
                # should not be overpowering (we have enough)
                {
                    "name": "vtherm7",
                    "device_power": 1000,
                    "is_device_active": True,
                    "is_over_climate": True,
                    "is_overpowering_detected": False,
                    "overpowering_state": STATE_UNKNOWN,
                },
            ],
            {"vtherm1": True, "vtherm2": True, "vtherm3": True, "vtherm6": True},
        ),
    ],
)
# @pytest.mark.skip
async def test_central_power_manageer_calculate_shedding(
    hass: HomeAssistant,
    current_power,
    current_max_power,
    vtherm_configs,
    expected_results,
):
    """Test the calculate_shedding of the CentralPowerManager"""
    vtherm_api: VersatileThermostatAPI = MagicMock(spec=VersatileThermostatAPI)
    central_power_manager = CentralFeaturePowerManager(hass, vtherm_api)

    registered_calls = {}

    def register_call(vtherm, overpowering):
        """Register a call to set_overpowering"""
        registered_calls.update({vtherm.name: overpowering})

    vtherms = []
    for vtherm_config in vtherm_configs:
        vtherm = MagicMock(spec=BaseThermostat)
        vtherm.name = vtherm_config.get("name")
        vtherm.is_device_active = vtherm_config.get("is_device_active")
        vtherm.is_over_climate = vtherm_config.get("is_over_climate")
        vtherm.nb_underlying_entities = vtherm_config.get("nb_underlying_entities")
        if not vtherm_config.get("is_over_climate"):
            vtherm.proportional_algorithm = MagicMock()
            vtherm.on_percent = vtherm.proportional_algorithm.on_percent = vtherm_config.get("on_percent")
        else:
            vtherm.on_percent = None
            vtherm.proportional_algorithm = None

        vtherm.power_manager = MagicMock(spec=FeaturePowerManager)
        vtherm.power_manager._vtherm = vtherm

        vtherm.power_manager.is_overpowering_detected = vtherm_config.get(
            "is_overpowering_detected"
        )
        vtherm.power_manager.device_power = vtherm_config.get("device_power")
        vtherm.power_manager.overpowering_state = vtherm_config.get("overpowering_state")

        async def mock_set_overpowering(
            overpowering, power_consumption_max=0, v=vtherm
        ):
            register_call(v, overpowering)

        vtherm.power_manager.set_overpowering = mock_set_overpowering

        vtherms.append(vtherm)

    # fmt:off
    with patch("custom_components.versatile_thermostat.central_feature_power_manager.CentralFeaturePowerManager.find_all_vtherm_with_power_management_sorted_by_dtemp", return_value=vtherms), \
        patch("custom_components.versatile_thermostat.central_feature_power_manager.CentralFeaturePowerManager.current_max_power", new_callable=PropertyMock, return_value=current_max_power), \
        patch("custom_components.versatile_thermostat.central_feature_power_manager.CentralFeaturePowerManager.current_power", new_callable=PropertyMock, return_value=current_power), \
        patch("custom_components.versatile_thermostat.central_feature_power_manager.CentralFeaturePowerManager.is_configured", new_callable=PropertyMock, return_value=True):
    # fmt:on

        await central_power_manager.calculate_shedding()

        # Check registered calls
        assert registered_calls == expected_results


@pytest.mark.parametrize(
    "dsecs, power, nb_call",
    [
        (0, 1000, 1),
        (0, None, 0),
        (0, STATE_UNAVAILABLE, 0),
        (0, STATE_UNKNOWN, 0),
        (21, 1000, 1),
        (19, 1000, 1),
    ],
)
async def test_central_power_manager_power_event(
    hass: HomeAssistant, dsecs, power, nb_call
):
    """Tests the Power sensor event"""
    vtherm_api: VersatileThermostatAPI = MagicMock(spec=VersatileThermostatAPI)
    central_power_manager = CentralFeaturePowerManager(hass, vtherm_api)

    assert central_power_manager.current_power is None
    assert central_power_manager.power_temperature is None
    assert central_power_manager.name == "centralPowerManager"

    # 2. post_init
    central_power_manager.post_init(
        {
            CONF_POWER_SENSOR: "sensor.power_entity_id",
            CONF_MAX_POWER_SENSOR: "sensor.max_power_entity_id",
            CONF_USE_POWER_FEATURE: True,
            CONF_PRESET_POWER: 13,
        }
    )

    assert central_power_manager.is_configured is True
    assert central_power_manager.current_max_power is None
    assert central_power_manager.current_power is None
    assert central_power_manager.power_temperature == 13

    # 3. start listening (not really useful but don't eat bread)
    await central_power_manager.start_listening()
    assert len(central_power_manager._active_listener) == 2

    now: datetime = NowClass.get_now(hass)
    # vtherm_api._set_now(now) vtherm_api is a MagicMock
    vtherm_api.now = now

    # 4. Call the _power_sensor_changed
    side_effects = SideEffects(
        {
            "sensor.power_entity_id": State("sensor.power_entity_id", power),
            "sensor.max_power_entity_id": State("sensor.max_power_entity_id", power),
        },
        State("unknown.entity_id", "unknown"),
    )
    # fmt:off
    with patch("homeassistant.core.StateMachine.get", side_effect=side_effects.get_side_effects()), \
         patch("custom_components.versatile_thermostat.central_feature_power_manager.CentralFeaturePowerManager.calculate_shedding", new_callable=AsyncMock) as mock_calculate_shedding:
    # fmt:on
        # set a default value to see if it has been replaced
        central_power_manager._current_power = -999
        await central_power_manager._power_sensor_changed(event=Event(
            event_type=EVENT_STATE_CHANGED,
            data={
                "entity_id": "sensor.power_entity_id",
                "new_state": State("sensor.power_entity_id", power),
                "old_state": State("sensor.power_entity_id", STATE_UNAVAILABLE),
            }))

        if nb_call > 0:
            await central_power_manager._do_immediate_shedding()

        expected_power = power if isinstance(power, (int, float)) else -999
        assert central_power_manager.current_power == expected_power
        assert mock_calculate_shedding.call_count == nb_call

    # Do another call x seconds later
    now = now + timedelta(seconds=dsecs)
    vtherm_api.now = now
    # fmt:off
    with patch("homeassistant.core.StateMachine.get", side_effect=side_effects.get_side_effects()), \
         patch("custom_components.versatile_thermostat.central_feature_power_manager.CentralFeaturePowerManager.calculate_shedding", new_callable=AsyncMock) as mock_calculate_shedding:
    # fmt:on
        central_power_manager._current_power = -999

        await central_power_manager._power_sensor_changed(event=Event(
            event_type=EVENT_STATE_CHANGED,
            data={
                "entity_id": "sensor.power_entity_id",
                "new_state": State("sensor.power_entity_id", power),
                "old_state": State("sensor.power_entity_id", STATE_UNAVAILABLE),
            }))

        if nb_call > 0:
            await central_power_manager._do_immediate_shedding()

        assert central_power_manager.current_power == expected_power
        assert mock_calculate_shedding.call_count == nb_call


@pytest.mark.parametrize(
    "dsecs, max_power, nb_call",
    [
        (0, 1000, 1),
        (0, None, 0),
        (0, STATE_UNAVAILABLE, 0),
        (0, STATE_UNKNOWN, 0),
        (21, 1000, 1),
        (19, 1000, 1),
    ],
)
async def test_central_power_manager_max_power_event(
    hass: HomeAssistant, dsecs, max_power, nb_call
):
    """Tests the Power sensor event"""
    vtherm_api: VersatileThermostatAPI = MagicMock(spec=VersatileThermostatAPI)
    central_power_manager = CentralFeaturePowerManager(hass, vtherm_api)

    assert central_power_manager.current_power is None
    assert central_power_manager.power_temperature is None
    assert central_power_manager.name == "centralPowerManager"

    # 2. post_init
    central_power_manager.post_init(
        {
            CONF_POWER_SENSOR: "sensor.power_entity_id",
            CONF_MAX_POWER_SENSOR: "sensor.max_power_entity_id",
            CONF_USE_POWER_FEATURE: True,
            CONF_PRESET_POWER: 13,
        }
    )

    assert central_power_manager.is_configured is True
    assert central_power_manager.current_max_power is None
    assert central_power_manager.current_power is None
    assert central_power_manager.power_temperature == 13

    # 3. start listening (not really useful but don't eat bread)
    await central_power_manager.start_listening()
    assert len(central_power_manager._active_listener) == 2

    now: datetime = NowClass.get_now(hass)
    # vtherm_api._set_now(now) vtherm_api is a MagicMock
    vtherm_api.now = now

    # 4. Call the _power_sensor_changed
    side_effects = SideEffects(
        {
            "sensor.power_entity_id": State("sensor.power_entity_id", max_power),
            "sensor.max_power_entity_id": State(
                "sensor.max_power_entity_id", max_power
            ),
        },
        State("unknown.entity_id", "unknown"),
    )
    # fmt:off
    with patch("homeassistant.core.StateMachine.get", side_effect=side_effects.get_side_effects()), \
         patch("custom_components.versatile_thermostat.central_feature_power_manager.CentralFeaturePowerManager.calculate_shedding", new_callable=AsyncMock) as mock_calculate_shedding:
    # fmt:on
        # set a default value to see if it has been replaced
        central_power_manager._current_max_power = -999
        await central_power_manager._power_sensor_changed(event=Event(
            event_type=EVENT_STATE_CHANGED,
            data={
                "entity_id": "sensor.max_power_entity_id",
                "new_state": State("sensor.max_power_entity_id", max_power),
                "old_state": State("sensor.max_power_entity_id", STATE_UNAVAILABLE),
            }))

        if nb_call > 0:
            await central_power_manager._do_immediate_shedding()

        expected_power = max_power if isinstance(max_power, (int, float)) else -999
        assert central_power_manager.current_max_power == expected_power
        assert mock_calculate_shedding.call_count == nb_call

    # Do another call x seconds later
    now = now + timedelta(seconds=dsecs)
    vtherm_api.now = now
    # fmt:off
    with patch("homeassistant.core.StateMachine.get", side_effect=side_effects.get_side_effects()), \
         patch("custom_components.versatile_thermostat.central_feature_power_manager.CentralFeaturePowerManager.calculate_shedding", new_callable=AsyncMock) as mock_calculate_shedding:
    # fmt:on
        central_power_manager._current_max_power = -999

        await central_power_manager._power_sensor_changed(event=Event(
            event_type=EVENT_STATE_CHANGED,
            data={
                "entity_id": "sensor.max_power_entity_id",
                "new_state": State("sensor.max_power_entity_id", max_power),
                "old_state": State("sensor.max_power_entity_id", STATE_UNAVAILABLE),
            }))

        if nb_call > 0:
            await central_power_manager._do_immediate_shedding()

        assert central_power_manager.current_max_power == expected_power
        assert mock_calculate_shedding.call_count == nb_call
