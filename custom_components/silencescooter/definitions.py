"""Definitions for the Silence Scooter integration."""
WRITABLE_SENSORS = {
    "scooter_last_trip_distance": {
        "name": "Distance du dernier trajet",
        "unit_of_measurement": "km",
        "icon": "mdi:map-marker-distance",
        "state_class": "measurement"
    },
    "scooter_last_trip_duration": {
        "name": "Durée du dernier trajet",
        "unit_of_measurement": "min",
        "icon": "mdi:clock-outline",
        "state_class": "measurement"
    },
    "scooter_last_trip_avg_speed": {
        "name": "Vitesse moyenne du dernier trajet",
        "unit_of_measurement": "km/h",
        "icon": "mdi:speedometer-medium",
        "state_class": "measurement"
    },
    "scooter_last_trip_max_speed": {
        "name": "Vitesse maximale du dernier trajet",
        "unit_of_measurement": "km/h",
        "icon": "mdi:speedometer",
        "state_class": "measurement"
    },
    "scooter_last_trip_battery_consumption": {
        "name": "Batterie consommée du dernier trajet",
        "unit_of_measurement": "%",
        "icon": "mdi:battery-clock",
        "state_class": "measurement"
    },
    "scooter_battery_display": {
        "name": "Niveau de batterie",
        "unit_of_measurement": "%",
        "device_class": "battery",
        "state_class": "measurement",
        "icon": "mdi:battery"
    },
    "scooter_odo_display": {
        "name": "Odomètre",
        "unit_of_measurement": "km",
        "icon": "mdi:counter",
        "state_class": "total_increasing"
    },
    "scooter_battery_percentage_regeneration": {
        "name": "Pourcentage énergie régénérée",
        "unit_of_measurement": "%",
        "icon": "mdi:battery-charging",
        "state_class": "measurement"
    }
}

INPUT_NUMBERS = {
    "scooter_pause_duration": {
        "name": "Durée totale des pauses",
        "min": 0,
        "max": 1440,
        "step": 0.1,
        "unit_of_measurement": "minutes"
    },
    "scooter_odo_debut": {
        "name": "Odomètre début de trajet",
        "initial": 0,
        "min": 0,
        "max": 100000,
        "step": 0.1
    },
    "scooter_odo_fin": {
        "name": "Odomètre fin de trajet",
        "min": 0,
        "max": 100000,
        "step": 0.1,
        "unit_of_measurement": "km"
    },
    "scooter_battery_soc_debut": {
        "name": "Batterie SOC début de trajet",
        "initial": 0,
        "min": 0,
        "max": 100,
        "step": 0.1,
        "unit_of_measurement": "%"
    },
    "scooter_battery_soc_fin": {
        "name": "Batterie SOC fin de trajet",
        "initial": 0,
        "min": 0,
        "max": 100,
        "step": 0.1,
        "unit_of_measurement": "%"
    },
    "scooter_tracked_distance": {
        "name": "Distance suivie (manuel)",
        "min": 0,
        "max": 100000,
        "step": 0.1,
        "unit_of_measurement": "km",
        "icon": "mdi:map-marker-path"
    },
    "scooter_tracked_battery_used": {
        "name": "Batterie suivie (manuel)",
        "min": 0,
        "max": 10000,
        "step": 0.1,
        "unit_of_measurement": "%",
        "icon": "mdi:battery-arrow-down-outline"
    },
    "scooter_energy_consumption_base": {
        "name": "Base consommation énergie scooter",
        "min": 0,
        "max": 1000,
        "step": 0.001,
        "unit_of_measurement": "kWh",
        "initial": 0
    },
}

INPUT_BOOLEANS = {
    "stop_trip_now": {
        "name": "Arrêter le trajet maintenant",
        "icon": "mdi:stop-circle"
    }
}

INPUT_DATETIMES = {
    "scooter_start_time": {
        "name": "Heure de départ dernier trajet",
        "has_date": True,
        "has_time": True
    },
    "scooter_end_time": {
        "name": "Heure de fin du dernier trajet",
        "has_date": True,
        "has_time": True
    },
    "scooter_last_moving_time": {
        "name": "Dernier instant en mouvement",
        "has_date": True,
        "has_time": True
    },
    "scooter_pause_start": {
        "name": "Début de la pause",
        "has_date": True,
        "has_time": True
    }
}

TRIGGER_SENSORS = {
    "scooter_start_time_iso": {
        "name": "Heure de départ ISO",
        "triggers": [
            {"platform": "state", "entity_id": "datetime.scooter_start_time"},
            {"platform": "time_pattern", "minutes": "/1"}
        ],
        "value_template": """
            {% if states('datetime.scooter_start_time') not in ['unknown', 'unavailable'] %}
                {% set dt = as_datetime(states('datetime.scooter_start_time')) %}
                {{ dt.strftime('%Y-%m-%dT%H:%M:%S') if dt else '' }}
            {% else %}
                {{ '' }}
            {% endif %}
        """
    },
    "scooter_history_start": {
        "name": "History Start",
        "triggers": [
            {
                "platform": "time_pattern",
                "minutes": "/1"
            },
            {
                "platform": "state",
                "entity_id": "datetime.scooter_end_time"
            }
        ],
        "value_template": """
            {% if states('datetime.scooter_end_time') not in ['unknown', 'unavailable'] %}
                {% set end_time = states('datetime.scooter_end_time') | as_datetime %}
                {% if end_time %}
                    {% set now_time = now() %}
                    {% set end_time_utc = end_time.replace(tzinfo=now_time.tzinfo) %}
                    {% if states('sensor.scooter_last_trip_duration') not in ['unknown', 'unavailable'] %}
                        {% set trip_duration = states('sensor.scooter_last_trip_duration') | float(0) %}
                        {% set adjusted_end_time = end_time_utc - timedelta(minutes=trip_duration) %}
                        {% set diff = now_time - adjusted_end_time %}
                        {{ ((diff.total_seconds() / 3600) | float) | round(0, 'ceil') }} hours ago
                    {% else %}
                        0 hours ago
                    {% endif %}
                {% else %}
                    0 hours ago
                {% endif %}
            {% else %}
                0 hours ago
            {% endif %}
        """
    },
    "scooter_trip_status": {
        "name": "État du trajet",
        "triggers": [
            {
                "platform": "state",
                "entity_id": "sensor.silence_scooter_status"
            },
            {
                "platform": "state",
                "entity_id": "sensor.silence_scooter_last_update"
            }
        ],
        "value_template": """
            {% set status_raw = states('sensor.silence_scooter_status') %}
            {% set last_update_str = states('sensor.silence_scooter_last_update') %}
            
            {% if status_raw not in ['unknown', 'unavailable'] and last_update_str not in ['unknown', 'unavailable'] %}
                {% set status = status_raw | float(default=None) %}
                {% set last_update = as_timestamp(last_update_str) %}
                {% set now_ts = as_timestamp(now()) %}
                {% if status is not none and status in [3.0, 4.0] and last_update and (now_ts - last_update) < 300 %}
                    on
                {% else %}
                    off
                {% endif %}
            {% else %}
                off
            {% endif %}
        """
    },
    "scooter_active_trip_duration": {
        "name": "Durée du trajet en cours",
        "unit_of_measurement": "minutes",
        "triggers": [
            {
                "platform": "time_pattern",
                "minutes": "/1"
            }
        ],
        "value_template": """
            {% set end_time_state = states('datetime.scooter_end_time') %}
            {% set start_time_state = states('datetime.scooter_start_time') %}
            {% set status = states('sensor.scooter_trip_status') %}
            
            {% if start_time_state not in ['unknown', 'unavailable'] %}
                {% set start_time = start_time_state | as_datetime %}
                {% if start_time %}
                    {% if status == 'on' %}
                        {{ ((now() - start_time).total_seconds() / 60) | round(0) }}
                    {% elif end_time_state not in ['unknown', 'unavailable'] %}
                        {% set end_time = end_time_state | as_datetime %}
                        {% if end_time %}
                            {{ ((end_time - start_time).total_seconds() / 60) | round(0) }}
                        {% else %}
                            0
                        {% endif %}
                    {% else %}
                        0
                    {% endif %}
                {% else %}
                    0
                {% endif %}
            {% else %}
                0
            {% endif %}
        """
    },
    "scooter_energy_consumption": {
        "name": "Consommation d'énergie",
        "unit_of_measurement": "kWh",
        "device_class": "energy",
        "state_class": "total_increasing",
        "triggers": [
            {
                "platform": "state",
                "entity_id": [
                    "sensor.silence_scooter_discharged_energy",
                    "sensor.silence_scooter_regenerated_energy"
                ]
            }
        ],
        "value_template": """
            {% set discharged_state = states('sensor.silence_scooter_discharged_energy') %}
            {% set regenerated_state = states('sensor.silence_scooter_regenerated_energy') %}
            {% set base_state = states('number.scooter_energy_consumption_base') %}
            {% set current_state = states('sensor.scooter_energy_consumption') %}

            {% if discharged_state not in ['unknown', 'unavailable'] and regenerated_state not in ['unknown', 'unavailable'] %}
                {% set discharged = discharged_state | float(0) %}
                {% set regenerated = regenerated_state | float(0) %}
                {% set max_variation = 5.6 %}
                {% set initial_value = base_state | float(0) if base_state not in ['unknown', 'unavailable'] else 0 %}

                {% if discharged > 0 and regenerated >= 0 %}
                    {% set new_value = discharged - regenerated %}
                    {% set current_value = current_state | float(initial_value) if current_state not in ['unknown', 'unavailable'] else initial_value %}
                    {% if current_value == initial_value %}
                        {{ new_value | round(3) }}
                    {% elif new_value > current_value and (new_value - current_value) <= max_variation %}
                        {{ new_value | round(3) }}
                    {% else %}
                        {{ current_value }}
                    {% endif %}
                {% else %}
                    {{ current_state | float(initial_value) if current_state not in ['unknown', 'unavailable'] else initial_value }}
                {% endif %}
            {% else %}
                {# When MQTT sensors are unavailable, KEEP the last known value instead of returning 0 #}
                {% set initial_value = base_state | float(0) if base_state not in ['unknown', 'unavailable'] else 0 %}
                {{ current_state | float(initial_value) if current_state not in ['unknown', 'unavailable'] else initial_value }}
            {% endif %}
        """
    }
}

TEMPLATE_SENSORS = {
    "scooter_status_display": {
        "name": "Status",
        "value_template": """
            {% set status_raw = states('sensor.silence_scooter_status') %}
            {% set status = status_raw | int(default=-1) %}
            
            {% if status == 0 %}
                Éteint
            {% elif status == 2 %}
                Allumage
            {% elif status == 3 %}
                Prêt à conduire
            {% elif status == 4 %}
                En mouvement
            {% elif status == 5 %}
                Sans batterie
            {% elif status == 6 %}
                Batterie en charge
            {% else %}
                Inconnu
            {% endif %}
        """,
        "icon_template": """
            {% set status_raw = states('sensor.silence_scooter_status') %}
            {% set status = status_raw | int(default=-1) %}
            {% if status == 0 %}
                mdi:power-off
            {% elif status == 2 %}
                mdi:engine
            {% elif status == 3 %}
                mdi:car
            {% elif status == 4 %}
                mdi:car-connected
            {% elif status == 5 %}
                mdi:battery-remove
            {% elif status == 6 %}
                mdi:power-plug-battery
            {% else %}
                mdi:alert-circle-outline
            {% endif %}
        """
    },
    "scooter_estimated_range": {
        "name": "Autonomie estimée",
        "unit_of_measurement": "km",
        "icon": "mdi:map-marker-distance",
        "value_template": """
            {% set battery_remaining = states('sensor.scooter_battery_display') | float(0) %}
            {% set consumption_per_km = states('sensor.scooter_battery_per_km') | float(0) %}
            {% if consumption_per_km > 0 and battery_remaining > 0 %}
                {{ (battery_remaining / consumption_per_km) | round(1) }}
            {% else %}
                0
            {% endif %}
        """
    },
    "scooter_battery_status": {
        "name": "Battery Status",
        "value_template": """
            {% if is_state('binary_sensor.silence_scooter_battery_in', 'on') %}
                Présente
            {% elif is_state('binary_sensor.silence_scooter_battery_in', 'off') %}
                Absente
            {% else %}
                Inconnu
            {% endif %}
        """,
        "icon_template": """
            {% if is_state('binary_sensor.silence_scooter_battery_in', 'on') %}
                mdi:battery
            {% elif is_state('binary_sensor.silence_scooter_battery_in', 'off') %}
                mdi:battery-off
            {% else %}
                mdi:alert-circle-outline
            {% endif %}
        """
    },
    "scooter_battery_per_km": {
        "name": "Consommation par km",
        "unit_of_measurement": "%/km",
        "state_class": "measurement",
        "icon": "mdi:battery-clock-outline",
        "value_template": """
            {% set odo = states('sensor.silence_scooter_odo') | float(0) %}
            {% set discharged = states('sensor.silence_scooter_discharged_energy') | float(0) %}
            {% set regenerated = states('sensor.silence_scooter_regenerated_energy') | float(0) %}
            {% set battery_capacity = 5.6 %}
            {% set net_consumption = [discharged - regenerated, 0] | max %}
            {% if odo > 0 and net_consumption > 0 %}
                {{ ((net_consumption / battery_capacity * 100) / odo) | round(2) }}
            {% else %}
                0
            {% endif %}
        """
    },
    "scooter_is_moving": {
        "name": "En mouvement",
        "value_template": """
            {% set status_raw = states('sensor.silence_scooter_status') %}
            {% set status = status_raw | float(default=None) %}
            {% set last_update_str = states('sensor.silence_scooter_last_update') %}
            {% if last_update_str not in ['unknown', 'unavailable', None] %}
                {% set last_update = as_timestamp(last_update_str) %}
                {% set now_ts = as_timestamp(now()) %}
                {% if status is not none and status in [3.0, 4.0] and (now_ts - last_update) < 300 %}
                    on
                {% else %}
                    off
                {% endif %}
            {% else %}
                off
            {% endif %}
        """
    },
    "scooter_end_time_relative": {
        "name": "Dernier trajet",
        "value_template": """
            {% set end_time = states('datetime.scooter_last_moving_time') %}
            {% if end_time != 'unknown' and end_time != '1970-01-01 00:00:00' %}
                Il y a {{ relative_time(as_datetime(end_time)) }}
            {% else %}
                Pas de trajet récent
            {% endif %}
        """
    }
}

ENERGY_COST_SENSORS = {
    "scooter_energy_cost_daily": {
        "name": "Coût quotidien de la recharge",
        "unit_of_measurement": "€",
        "state_class": "measurement",
        "value_template": """
            {% set consumption = states('sensor.scooter_energy_consumption_daily') | float(0) %}
            {% set price_per_kwh = states('sensor.tarif_base_ttc') | float(0.215) %}
            {{ (consumption * price_per_kwh) | round(2) }}
        """
    },
    "scooter_energy_cost_weekly": {
        "name": "Coût hebdo de la recharge",
        "unit_of_measurement": "€",
        "state_class": "measurement",
        "value_template": """
            {% set consumption = states('sensor.scooter_energy_consumption_weekly') | float(0) %}
            {% set price_per_kwh = states('sensor.tarif_base_ttc') | float(0.215) %}
            {{ (consumption * price_per_kwh) | round(2) }}
        """
    },
    "scooter_energy_cost_monthly": {
        "name": "Coût mensuel de la recharge",
        "unit_of_measurement": "€",
        "state_class": "measurement",
        "value_template": """
            {% set consumption = states('sensor.scooter_energy_consumption_monthly') | float(0) %}
            {% set price_per_kwh = states('sensor.tarif_base_ttc') | float(0.215) %}
            {{ (consumption * price_per_kwh) | round(2) }}
        """
    },
    "scooter_energy_cost_yearly": {
        "name": "Coût annuel de la recharge",
        "unit_of_measurement": "€",
        "state_class": "measurement",
        "value_template": """
            {% set consumption = states('sensor.scooter_energy_consumption_yearly') | float(0) %}
            {% set price_per_kwh = states('sensor.tarif_base_ttc') | float(0.215) %}
            {{ (consumption * price_per_kwh) | round(2) }}
        """
    }
}

BATTERY_HEALTH_SENSORS = {
    "scooter_battery_cell_imbalance": {
        "name": "Batterie - Déséquilibre cellules",
        "unit_of_measurement": "mV",
        "state_class": "measurement",
        "icon": "mdi:battery-alert-variant-outline",
        "value_template": """
            {% set raw = [
                states('sensor.silence_scooter_cell1_voltage'),
                states('sensor.silence_scooter_cell2_voltage'),
                states('sensor.silence_scooter_cell3_voltage'),
                states('sensor.silence_scooter_cell4_voltage'),
                states('sensor.silence_scooter_cell5_voltage'),
                states('sensor.silence_scooter_cell6_voltage'),
                states('sensor.silence_scooter_cell7_voltage'),
                states('sensor.silence_scooter_cell8_voltage'),
                states('sensor.silence_scooter_cell9_voltage'),
                states('sensor.silence_scooter_cell10_voltage'),
                states('sensor.silence_scooter_cell11_voltage'),
                states('sensor.silence_scooter_cell12_voltage'),
                states('sensor.silence_scooter_cell13_voltage'),
                states('sensor.silence_scooter_cell14_voltage')
            ] %}
            {% set valid = raw | reject('in', ['unknown', 'unavailable', 'None', ''])
                               | map('float', default=none)
                               | reject('none')
                               | select('greaterthan', 0)
                               | list %}
            {% if valid | length >= 2 %}
                {{ ((valid | max - valid | min) * 1000) | round(0) }}
            {% else %}
                {{ states('sensor.scooter_battery_cell_imbalance') if states('sensor.scooter_battery_cell_imbalance') not in ['unknown', 'unavailable'] else 'unavailable' }}
            {% endif %}
        """
    },
    "scooter_battery_soc_calculated": {
        "name": "Batterie - SOC calculé (Voltage)",
        "unit_of_measurement": "%",
        "state_class": "measurement",
        "device_class": "battery",
        "icon": "mdi:battery-charging-outline",
        "value_template": """
            {% set volt = states('sensor.silence_scooter_battery_volt') | float(0) %}
            {# NMC 14S Li-ion lookup table: cell voltage (OCV) -> SOC%
               Based on typical NMC discharge curve at C/5, 25C #}
            {% if volt <= 0 %}
                {{ states('sensor.scooter_battery_soc_calculated') if states('sensor.scooter_battery_soc_calculated') not in ['unknown', 'unavailable'] else 'unavailable' }}
            {% else %}
                {% set cell_v = volt / 14 %}
                {% set lut = [
                    (2.80, 0), (3.00, 1), (3.10, 3), (3.20, 5),
                    (3.30, 10), (3.40, 15), (3.50, 25), (3.55, 30),
                    (3.60, 38), (3.65, 45), (3.70, 55), (3.75, 65),
                    (3.80, 72), (3.85, 78), (3.90, 84), (3.95, 89),
                    (4.00, 93), (4.05, 96), (4.10, 98), (4.15, 99),
                    (4.20, 100)
                ] %}
                {% if cell_v <= lut[0][0] %}
                    0
                {% elif cell_v >= lut[-1][0] %}
                    100
                {% else %}
                    {% set ns = namespace(soc=0) %}
                    {% for i in range(lut | length - 1) %}
                        {% if cell_v >= lut[i][0] and cell_v < lut[i+1][0] %}
                            {% set ratio = (cell_v - lut[i][0]) / (lut[i+1][0] - lut[i][0]) %}
                            {% set ns.soc = lut[i][1] + ratio * (lut[i+1][1] - lut[i][1]) %}
                        {% endif %}
                    {% endfor %}
                    {{ ns.soc | round(1) }}
                {% endif %}
            {% endif %}
        """
    },
    "scooter_battery_soc_deviation": {
        "name": "Batterie - Écart SOC affiché/calculé",
        "unit_of_measurement": "%",
        "state_class": "measurement",
        "icon": "mdi:delta",
        "value_template": """
            {% set displayed_st = states('sensor.scooter_battery_display') %}
            {% set calculated_st = states('sensor.scooter_battery_soc_calculated') %}
            {% if displayed_st not in ['unknown', 'unavailable'] and calculated_st not in ['unknown', 'unavailable'] %}
                {% set soc_displayed = displayed_st | float(0) %}
                {% set soc_calculated = calculated_st | float(0) %}
                {% if soc_displayed > 0 or soc_calculated > 0 %}
                    {{ (soc_displayed - soc_calculated) | round(1) }}
                {% else %}
                    unavailable
                {% endif %}
            {% else %}
                unavailable
            {% endif %}
        """
    },
    "scooter_battery_charge_cycles": {
        "name": "Batterie - Cycles de charge cumulés",
        "unit_of_measurement": "cycles",
        "state_class": "total_increasing",
        "icon": "mdi:battery-sync",
        "value_template": """
            {% set charged_state = states('sensor.silence_scooter_charged_energy') %}
            {% set battery_capacity = 5.6 %}
            {% set current = states('sensor.scooter_battery_charge_cycles') %}
            {% if charged_state not in ['unknown', 'unavailable'] %}
                {% set charged = charged_state | float(0) %}
                {% if charged > 0 %}
                    {{ (charged / battery_capacity) | round(1) }}
                {% else %}
                    {{ current if current not in ['unknown', 'unavailable'] else 0 }}
                {% endif %}
            {% else %}
                {{ current if current not in ['unknown', 'unavailable'] else 0 }}
            {% endif %}
        """
    }
}

USAGE_STATISTICS_SENSORS = {
    "scooter_distance_per_charge": {
        "name": "Utilisation - Distance moy. par cycle",
        "unit_of_measurement": "km",
        "state_class": "measurement",
        "icon": "mdi:map-marker-distance",
        "value_template": """
            {% set odo = states('sensor.silence_scooter_odo') | float(0) %}
            {% set charged = states('sensor.silence_scooter_charged_energy') | float(0) %}
            {% set battery_capacity = 5.6 %}
            {% if charged > 0 and odo > 0 %}
                {{ (odo / (charged / battery_capacity)) | round(1) }}
            {% else %}
                0
            {% endif %}
        """
    },
    "scooter_cost_per_km": {
        "name": "Utilisation - Coût au kilomètre",
        "unit_of_measurement": "€/km",
        "state_class": "measurement",
        "icon": "mdi:currency-eur",
        "value_template": """
            {% set odo = states('sensor.silence_scooter_odo') | float(0) %}
            {% set consumed = states('sensor.silence_scooter_discharged_energy') | float(0) %}
            {% set regenerated = states('sensor.silence_scooter_regenerated_energy') | float(0) %}
            {% set price_per_kwh = states('sensor.tarif_base_ttc') | float(0.215) %}
            {% if odo > 0 %}
                {{ (((consumed - regenerated) * price_per_kwh) / odo) | round(3) }}
            {% else %}
                0
            {% endif %}
        """
    },
    "scooter_average_trip_distance": {
        "name": "Utilisation - Distance moyenne par trajet",
        "unit_of_measurement": "km",
        "state_class": "measurement",
        "icon": "mdi:map-marker-path",
        "value_template": """
            {% set trips = state_attr('sensor.scooter_trips', 'history') %}
            {% if trips is not none and trips | length > 0 %}
                {% set total = trips | map(attribute='distance') | map('float') | sum %}
                {{ (total / (trips | length)) | round(1) }}
            {% else %}
                0
            {% endif %}
        """
    }
}

UTILITY_METERS = {
    "scooter_energy_consumption_daily": {
        "source": "sensor.scooter_energy_consumption",
        "cycle": "daily",
        "name": "Scooter Energy Consumption Daily"
    },
    "scooter_energy_consumption_weekly": {
        "source": "sensor.scooter_energy_consumption",
        "cycle": "weekly",
        "name": "Scooter Energy Consumption Weekly"
    },
    "scooter_energy_consumption_monthly": {
        "source": "sensor.scooter_energy_consumption",
        "cycle": "monthly",
        "name": "Scooter Energy Consumption Monthly"
    },
    "scooter_energy_consumption_yearly": {
        "source": "sensor.scooter_energy_consumption",
        "cycle": "yearly",
        "name": "Scooter Energy Consumption Yearly"
    }
}