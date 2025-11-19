import logging
import time
import socket
from typing import Optional

from cli_base.tyro_commands import TyroVerbosityArgType
from ha_services.mqtt4homeassistant.mqtt import get_connected_client
from rich import (
    get_console,
    print,  # noqa
)
from tinkerforge.ip_connection import IPConnection

from tinkerforge2mqtt.cli_app import app
from tinkerforge2mqtt.cli_app.settings import get_user_settings
from tinkerforge2mqtt.device_registry.devices_handler import DevicesHandler
from tinkerforge2mqtt.user_settings import UserSettings


logger = logging.getLogger(__name__)


def setup_logging(*, verbosity: TyroVerbosityArgType, log_format: str = '%(message)s'):  # Move to cli_tools
    if verbosity == 0:
        level = logging.ERROR
    elif verbosity == 1:
        level = logging.WARNING
    elif verbosity == 2:
        level = logging.INFO
    else:
        level = logging.DEBUG
        if '%(name)s' not in log_format:
            log_format = f'(%(name)s) {log_format}'

    console = get_console()
    console.print(f'(Set log level {verbosity}: {logging.getLevelName(level)})', justify='right')
    logging.basicConfig(
        level=level,
        format=log_format,
        datefmt='[%x %X.%f]',
        # handlers=[
        #     RichHandler(console=console, omit_repeated_times=False,
        #     log_time_format='[%x FOO %X]'
        #
        # )],
        force=True,
    )


def connect_with_retry(ipcon: IPConnection, connect_kwargs: dict, max_retries: Optional[int] = None, initial_delay: float = 1.0) -> bool:
    """
    Connect to Tinkerforge with retry logic and exponential backoff.

    Args:
        ipcon: IPConnection instance
        connect_kwargs: Connection parameters
        max_retries: Maximum number of retries (None for infinite retries)
        initial_delay: Initial delay between retries in seconds

    Returns:
        True if connected successfully
    """
    attempt = 0
    delay = initial_delay

    while max_retries is None or attempt <= max_retries:
        try:
            print(f'Connecting to {connect_kwargs} (attempt {attempt + 1})')
            ipcon.connect(**connect_kwargs)
            print('✓ Connected successfully!')
            return True
        except (TimeoutError, socket.timeout, ConnectionError, OSError) as e:
            attempt += 1
            if max_retries is not None and attempt > max_retries:
                print(f'✗ Failed to connect after {max_retries} attempts. Last error: {e}')
                return False

            print(f'✗ Connection failed: {e}. Retrying in {delay:.1f} seconds...')
            time.sleep(delay)

            # Exponential backoff with jitter, max 60 seconds
            delay = min(delay * 1.5, 60.0)

    return False


def connect_mqtt_with_retry(user_settings: UserSettings, verbosity: TyroVerbosityArgType, max_retries: Optional[int] = None, initial_delay: float = 1.0):
    """
    Connect to MQTT with retry logic and exponential backoff.

    Args:
        user_settings: User settings containing MQTT configuration
        verbosity: Verbosity level for logging
        max_retries: Maximum number of retries (None for infinite retries)
        initial_delay: Initial delay between retries in seconds

    Returns:
        Connected MQTT client or None if failed
    """
    attempt = 0
    delay = initial_delay

    while max_retries is None or attempt <= max_retries:
        try:
            print(f'Connecting to MQTT (attempt {attempt + 1})')
            mqtt_client = get_connected_client(settings=user_settings.mqtt, verbosity=verbosity)
            print('✓ MQTT connected successfully!')
            return mqtt_client
        except (TimeoutError, socket.timeout, ConnectionError, OSError) as e:
            attempt += 1
            if max_retries is not None and attempt > max_retries:
                print(f'✗ Failed to connect to MQTT after {max_retries} attempts. Last error: {e}')
                return None

            print(f'✗ MQTT connection failed: {e}. Retrying in {delay:.1f} seconds...')
            time.sleep(delay)

            # Exponential backoff with jitter, max 60 seconds
            delay = min(delay * 1.5, 60.0)

    return None


@app.command
def publish_loop(verbosity: TyroVerbosityArgType):
    """
    Publish Tinkerforge devices events via MQTT to Home Assistant.
    """
    setup_logging(verbosity=verbosity, log_format='%(levelname)s %(processName)s %(threadName)s %(message)s')
    user_settings: UserSettings = get_user_settings(verbosity=verbosity)

    # https://www.tinkerforge.com/en/doc/Software/IPConnection_Python.html
    connect_kwargs = dict(
        host=user_settings.host,
        port=user_settings.port,
    )

    # Connect to MQTT with retry logic - never give up!
    mqtt_client = connect_mqtt_with_retry(user_settings, verbosity, max_retries=None)
    if mqtt_client is None:
        print("Failed to establish MQTT connection. Exiting.")
        return

    mqtt_client.loop_start()

    # Main connection and operation loop - never give up!
    while True:
        ipcon = IPConnection()
        devices_handler = None

        try:
            # Connect with retry logic - for main loop, never give up (max_retries=None)
            if not connect_with_retry(ipcon, connect_kwargs, max_retries=None):
                # This should never happen with max_retries=None, but just in case
                print("Unexpected connection failure, retrying...")
                continue

            # Setup devices handler after successful connection
            devices_handler = DevicesHandler(ipcon, mqtt_client=mqtt_client, user_settings=user_settings)
            ipcon.register_callback(IPConnection.CALLBACK_ENUMERATE, devices_handler)

            # Main operation loop
            while True:
                try:
                    ipcon.enumerate()
                    time.sleep(5)
                except KeyboardInterrupt:
                    logger.info('Keyboard interrupt')
                    ipcon.disconnect()
                    mqtt_client.disconnect()
                    return  # Exit the entire function
                except (TimeoutError, socket.timeout, ConnectionError, OSError) as e:
                    logger.warning(f'Connection lost during operation: {e}. Will reconnect...')
                    break  # Break inner loop to reconnect

        except KeyboardInterrupt:
            logger.info('Keyboard interrupt during connection setup')
            try:
                if ipcon:
                    ipcon.disconnect()
                if mqtt_client:
                    mqtt_client.disconnect()
            except Exception:
                pass
            return  # Exit the entire function

        except Exception as e:
            logger.error(f'Unexpected error during connection/operation: {e}. Will retry...')

        # Always clean up before reconnection attempt
        try:
            if ipcon:
                ipcon.disconnect()
        except Exception:
            pass  # Ignore disconnect errors

        logger.info('Preparing to reconnect...')
        time.sleep(1)  # Brief pause before reconnection attempt
