from datetime import date, datetime


def today() -> date:
    """Today in server-local time; a function so tests can freeze it (patch `_clock.today`)."""
    return datetime.now().astimezone().date()
