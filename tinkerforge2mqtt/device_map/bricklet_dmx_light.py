import logging

from ha_services.mqtt4homeassistant.components.light import Light
from paho.mqtt.client import Client
from tinkerforge.bricklet_dmx import BrickletDMX

from tinkerforge2mqtt.device_map import register_map_class
from tinkerforge2mqtt.device_map_utils.base import DeviceMapBase
from tinkerforge2mqtt.device_map_utils.utils import print_exception_decorator


logger = logging.getLogger(__name__)


@register_map_class()
class BrickletDMXMapper(DeviceMapBase):
    # https://www.tinkerforge.com/de/doc/Software/Bricklets/DMX_Bricklet_Python.html

    device_identifier = BrickletDMX.DEVICE_IDENTIFIER

    def __init__(self, *, device: BrickletDMX, **kwargs):
        self.device: BrickletDMX = device
        self.dmx_frame = [0] * 512  # DMX frame with 512 channels
        super().__init__(device=device, **kwargs)

    @print_exception_decorator
    def setup_sensors(self):
        super().setup_sensors()

        self.dmx_light = Light(
            device=self.mqtt_device,
            name='DMX Light',
            uid='dmx_light',
            callback_brightness=self.brightness_callback,
            callback_switch=self.switch_callback,
            callback_rgb=self.rgb_callback,
            default_brightness=100, #
            min_brightness=0,
            max_brightness=255,
        )
        logger.info(f'Creating: {self.dmx_light}')

    @print_exception_decorator
    def setup_callbacks(self):
        logger.info(f'setup_callbacks {self}')
        super().setup_callbacks()

        try:
            # Set DMX mode to master (sending DMX data)
            self.device.set_dmx_mode(self.device.DMX_MODE_MASTER)
            logger.info(f'DMX mode set to master (UID: {self.device.uid_string})')
        except Exception as e:
            logger.error(f'Failed to set DMX mode: {e}')

    @print_exception_decorator
    def poll(self):
        super().poll()
        # DMX lights don't need regular polling for state updates
        # The light state is maintained by the device itself
        self.dmx_light.publish(self.mqtt_client)

    @print_exception_decorator
    def switch_callback(self, *, client: Client, component: Light, old_state: str, new_state: str):
        logger.info(f'{component.name} switch state changed: {old_state!r} -> {new_state!r}')

        try:
            is_on = new_state == component.ON

            if is_on:
                # Turn on: restore previous brightness and color values
                # Use current component states for brightness and RGB
                brightness = getattr(component, 'state_brightness', 100)
                rgb = getattr(component, 'state_rgb', [255, 255, 255])

                self.set_rgb_fixture(1, rgb=rgb, brightness=brightness)
                logger.info(f'DMX light turned ON - RGB: (brightness: {brightness}%)')

            else:
                # Turn off - set RGB channels to 0
                self.dmx_frame[0] = 0
                self.dmx_frame[1] = 0
                self.dmx_frame[2] = 0
                logger.info('DMX light turned OFF')

            # Send DMX frame
            self.device.write_frame(self.dmx_frame)

            # Update component state and publish
            component.set_state_switch(new_state)
        except Exception as e:
            logger.error(f'Failed to control DMX switch: {e}')
        self.poll()

    @print_exception_decorator
    def rgb_callback(self, *, client: Client, component: Light, old_state: list[int], new_state: list[int]):
        logger.info(f'{component.name} RGB state changed: {old_state!r} -> {new_state!r}')

        try:
            # Check if light is currently on
            switch_state = getattr(component, 'state_switch', component.ON)
            is_on = switch_state == component.ON

            if is_on:
                # Get current brightness for scaling
                brightness = getattr(component, 'state_brightness', 100)
                self.set_rgb_fixture(start_channel=1, rgb=new_state,brightness=brightness)


                logger.info(f'DMX RGB updated:(raw: {new_state}, brightness: {brightness}%)')
            else:
                logger.info(f'DMX RGB updated but light is off - storing color: {new_state}')
                self.set_rgb_fixture(start_channel=1, rgb=new_state,brightness=0)
            # Update component state and publish
            component.set_state_rgb(new_state)
        except Exception as e:
            logger.error(f'Failed to control DMX RGB: {e}')
        self.poll()

    @print_exception_decorator
    def brightness_callback(self, *, client: Client, component: Light, old_state: int, new_state: int):
        logger.info(f'{component.name} brightness state changed: {old_state!r} -> {new_state!r}')

        try:
            # Check if light is currently on
            switch_state = getattr(component, 'state_switch', component.ON)
            is_on = switch_state == component.ON

            if is_on:
                # Get current RGB values
                rgb = getattr(component, 'state_rgb', [255, 255, 255])

            else:
                logger.info(f'DMX brightness updated but light is off - storing brightness: {new_state}%')

            # Update component state and publish
            component.set_state_brightness(new_state)

        except Exception as e:
            logger.error(f'Failed to control DMX brightness: {e}')
        self.poll()

    @print_exception_decorator
    def set_dmx_channel(self, channel: int, value: int):
        """Set a specific DMX channel value (1-512)"""
        if 1 <= channel <= 512 and 0 <= value <= 255:
            self.dmx_frame[channel - 1] = value  # DMX channels are 1-based
            try:
                self.device.write_frame(self.dmx_frame)
                logger.info(f'DMX channel {channel} set to {value}')
            except Exception as e:
                logger.error(f'Failed to set DMX channel {channel}: {e}')
        else:
            logger.error(f'Invalid DMX channel ({channel}) or value ({value})')

    @print_exception_decorator
    def set_rgb_fixture(self, start_channel: int, rgb: list[int], brightness:int=100):
        b_factor = brightness / 255.0
        r, g, b = rgb
        r = int(r * b_factor)
        g = int(g * b_factor)
        b = int(b * b_factor)
        """Set RGB values for a fixture starting at the given channel"""
        if 1 <= start_channel <= 510:  # Need at least 3 channels
            self.dmx_frame[start_channel] = r
            self.dmx_frame[start_channel + 1] = g
            self.dmx_frame[start_channel + 2] = b
            try:
                self.device.write_frame(self.dmx_frame)
                logger.info(f'RGB fixture at channel {start_channel} set to R={r}, G={g}, B={b}')
            except Exception as e:
                logger.error(f'Failed to set RGB fixture: {e}')
        else:
            logger.error(f'Invalid start channel for RGB fixture: {start_channel}')
