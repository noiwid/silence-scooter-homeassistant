"""Heure de mesure des relevés du scooter (sans dépendance à Home Assistant, donc testable)."""
from datetime import datetime, timedelta


def usable_record_time(
    state: str | None,
    now: datetime,
    max_age: timedelta,
    not_before: datetime | None = None,
) -> datetime | None:
    """Heure de MESURE du dernier relevé si elle est exploitable, sinon None.

    `state` est l'état de sensor.silence_scooter_record_time (ISO avec fuseau),
    publié par le serveur. Le module livre parfois des relevés restés en
    attente pendant des heures : une heure trop vieille (`max_age`), dans le
    futur, ou antérieure au départ du trajet (`not_before`) ne doit pas dater
    un événement du trajet en cours.
    """
    if not state or state in ("unknown", "unavailable"):
        return None
    try:
        record_dt = datetime.fromisoformat(state)
    except (ValueError, TypeError):
        return None
    if record_dt.tzinfo is None:
        return None
    if record_dt > now + timedelta(minutes=1) or record_dt < now - max_age:
        return None
    if not_before is not None and record_dt < not_before:
        return None
    return record_dt
