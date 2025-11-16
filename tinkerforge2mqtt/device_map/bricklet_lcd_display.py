import logging

from ha_services.mqtt4homeassistant.components.text import Text
from paho.mqtt.client import Client
from tinkerforge.bricklet_lcd_128x64 import BrickletLCD128x64

from tinkerforge2mqtt.device_map import register_map_class
from tinkerforge2mqtt.device_map_utils.base import DeviceMapBase
from tinkerforge2mqtt.device_map_utils.utils import print_exception_decorator


logger = logging.getLogger(__name__)


@register_map_class()
class BrickletLCD128x64Mapper(DeviceMapBase):
    # https://www.tinkerforge.com/de/doc/Software/Bricklets/LCD128x64_Bricklet_Python.html
    device_identifier = BrickletLCD128x64.DEVICE_IDENTIFIER

    def __init__(self, *, device: BrickletLCD128x64, **kwargs):
        self.device: BrickletLCD128x64 = device
        super().__init__(device=device, **kwargs)

    @print_exception_decorator
    def setup_sensors(self):
        super().setup_sensors()

        # Single Text component for LCD display
        self.lcd_display = Text(
            device=self.mqtt_device,
            name='LCD Display',
            uid='display',
            callback=self.display_callback,
        )
        logger.info(f'Creating: {self.lcd_display}')

    @print_exception_decorator
    def setup_callbacks(self):
       pass  # TODO

    @print_exception_decorator
    def poll(self):
        super().poll()
        # LCD displays don't need regular polling for state updates
        # The display state is maintained by the device itself
        self.lcd_display.publish(self.mqtt_client)


    @print_exception_decorator
    def display_callback(self, *, client: Client, component: Text, old_state: str, new_state: str):
        logger.info(f'{component.name} text changed: {old_state!r} -> {new_state!r}')

        # Split text into lines (max 4 lines, 21 chars each)
        lines = new_state.split('\\n')

        try:
            # Clear display first
            self.device.clear_display()
            # Write up to 4 lines
            for line_num, line_text in enumerate(lines[:4]):
                if line_text:  # Only write non-empty lines
                    # Truncate to 21 characters per line
                    truncated_text = line_text[:21]
                    self.device.write_line(line_num, 0, truncated_text)
                    logger.info(f'LCD line {line_num} updated: {truncated_text}')
            logger.info(f'LCD display updated with {len(lines[:4])} lines')
            self.lcd_display.set_state(new_state)
        except Exception as e:
            self.device.write_line(0, 0, 'Fail to write LCD')
            self.lcd_display.set_state('Fail to write LCD')
            logger.error(f'Failed to write to LCD display: {e}')

        self.poll()  # Refresh state after update
