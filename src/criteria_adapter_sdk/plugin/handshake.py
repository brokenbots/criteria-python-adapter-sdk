"""Handshake validation for Criteria plugins.

Criteria uses HashiCorp's go-plugin protocol which requires a "magic cookie"
handshake to ensure the plugin process was started by a legitimate Criteria
host process.
"""

import os
import sys

MAGIC_COOKIE_KEY = "CRITERIA_PLUGIN"
MAGIC_COOKIE_VALUE = "7a1bf31f-c805-4e75-a31c-22195c9fdd4c"
PROTOCOL_VERSION = 1


def validate_handshake() -> bool:
    """Validate the handshake cookie.

    If the CRITERIA_PLUGIN environment variable is not set or has the wrong
    value, the plugin should exit immediately. This prevents accidental
    execution of plugin binaries as standalone programs.

    Returns:
        True if handshake is valid.

    Raises:
        RuntimeError: If handshake fails.
    """
    cookie = os.environ.get(MAGIC_COOKIE_KEY)

    if cookie is None:
        raise RuntimeError(
            f"Missing {MAGIC_COOKIE_KEY} environment variable. "
            "This binary must be started by the Criteria plugin host."
        )

    if cookie != MAGIC_COOKIE_VALUE:
        raise RuntimeError(
            f"Invalid {MAGIC_COOKIE_KEY} value. "
            f'Expected "{MAGIC_COOKIE_VALUE}", got "{cookie}".'
        )

    return True


def is_plugin_invocation() -> bool:
    """Check if running as a plugin (has valid handshake).

    Non-throwing version for detection.

    Returns:
        True if this is a plugin invocation.
    """
    return os.environ.get(MAGIC_COOKIE_KEY) == MAGIC_COOKIE_VALUE


def validate_and_exit_on_failure() -> None:
    """Validate handshake and exit if invalid.

    This function validates the handshake and exits the process with code 1
    if it fails. Use this at the very start of your plugin's main() function.
    """
    try:
        validate_handshake()
    except RuntimeError as err:
        print(err, file=sys.stderr)
        sys.exit(1)
