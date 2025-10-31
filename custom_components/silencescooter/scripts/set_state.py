state = data.get("entity_id")
attributes = data.get("attributes", {})

if state:
    current_state = hass.states.get(state)
    new_state = current_state.state if current_state else "unknown"
    hass.states.set(state, new_state, attributes)