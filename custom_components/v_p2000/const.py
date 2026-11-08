"""Constants for V-P2000."""

DOMAIN = "v_p2000"
NAME = "V-P2000"
VERSION = "1.0.0"

EVENT_ALARM = f"{DOMAIN}_alarm"

API_URL = "https://beta.alarmeringdroid.nl/api2/find/"
USER_AGENT = f"{NAME}/{VERSION} (Home Assistant integration)"

CONF_GROEPEN = "groepen"
CONF_GROEPEN_TEKST = "groepen_tekst"
CONF_SCAN_INTERVAL = "scan_interval"

DEFAULT_SCAN_INTERVAL = 10
MIN_SCAN_INTERVAL = 5
MAX_SCAN_INTERVAL = 300

# Query time depends on the capcodes (0.3 s for some, ~17 s for busy monitor codes), so allow slow
# answers; the next poll then waits at least SLOW_FACTOR x the last request time.
REQUEST_TIMEOUT = 20
SLOW_FACTOR = 2
MAX_BACKOFF = 15  # seconds between attempts while AlarmeringDroid is failing
MAX_RETRY_AFTER = 120  # cap for a Retry-After header on 429/503
OFFLINE_AFTER = 60  # seconds without a successful poll -> connection sensor off

# After a (re)start: only alarm for unseen meldingen at most this many minutes old.
RECENT_MINUTES = 5
MAX_SEEN = 500


def signal_alarm(entry_id: str) -> str:
    return f"{DOMAIN}_{entry_id}_alarm"


def signal_status(entry_id: str) -> str:
    return f"{DOMAIN}_{entry_id}_status"
