import logging

from ha_services.mqtt4homeassistant.components.light import Light
from paho.mqtt.client import Client
from tinkerforge.bricklet_dmx import BrickletDMX

from tinkerforge2mqtt.device_map import register_map_class
from tinkerforge2mqtt.device_map_utils.base import DeviceMapBase
from tinkerforge2mqtt.device_map_utils.utils import print_exception_decorator


logger = logging.getLogger(__name__)

MAX_BRIGHTNESS = 255

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
            callback_rgbw=self.rgbw_callback,
            default_brightness=100,
            min_brightness=0,
            max_brightness=MAX_BRIGHTNESS,
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
            rgbw = getattr(component, 'state_rgbw', [MAX_BRIGHTNESS, MAX_BRIGHTNESS, MAX_BRIGHTNESS, MAX_BRIGHTNESS])
            if is_on:
                # Turn on: restore previous brightness and color values
                # Use current component states for brightness and RGBW
                brightness = getattr(component, 'state_brightness', MAX_BRIGHTNESS)

                self.set_rgbw_fixture(1, rgbw=rgbw, brightness=brightness)
                logger.info(f'DMX light turned ON - RGBW: (brightness: {brightness}%)')

            else:
                self.set_rgbw_fixture(1, rgbw=rgbw, brightness=0)
                logger.info('DMX light turned OFF')

            # Send DMX frame
            self.device.write_frame(self.dmx_frame)

            # Update component state and publish
            component.set_state_switch(new_state)
        except Exception as e:
            logger.error(f'Failed to control DMX switch: {e}')
        self.poll()

    @print_exception_decorator
    def rgbw_callback(self, *, client: Client, component: Light, old_state: list[int], new_state: list[int]):
        logger.info(f'{component.name} RGBW state changed: {old_state!r} -> {new_state!r}')

        try:
            # Check if light is currently on
            switch_state = getattr(component, 'state_switch', component.ON)
            is_on = switch_state == component.ON

            if is_on:
                # Get current brightness for scaling
                brightness = getattr(component, 'state_brightness', MAX_BRIGHTNESS)
                self.set_rgbw_fixture(start_channel=1, rgbw=new_state,brightness=brightness)


                logger.info(f'DMX RGB updated:(raw: {new_state}, brightness: {brightness}%)')
            else:
                logger.info(f'DMX RGB updated but light is off - storing color: {new_state}')
                self.set_rgbw_fixture(start_channel=1, rgbw=new_state,brightness=0)
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
            # Update component state and publish
            component.set_state_brightness(new_state)

        except Exception as e:
            logger.error(f'Failed to control DMX brightness: {e}')
        self.poll()

    @print_exception_decorator
    def set_dmx_channel(self, channel: int, value: int):
        """Set a specific DMX channel value (1-512)"""
        if 1 <= channel <= 512 and 0 <= value <= MAX_BRIGHTNESS:
            self.dmx_frame[channel - 1] = value  # DMX channels are 1-based
            try:
                self.device.write_frame(self.dmx_frame)
                logger.info(f'DMX channel {channel} set to {value}')
            except Exception as e:
                logger.error(f'Failed to set DMX channel {channel}: {e}')
        else:
            logger.error(f'Invalid DMX channel ({channel}) or value ({value})')

    @print_exception_decorator
    def set_rgbw_fixture(self, start_channel: int, rgbw: list[int], brightness:int=100):
        b_factor = brightness / MAX_BRIGHTNESS
        r, g, b, w = rgbw
        r = int(r * b_factor)
        g = int(g * b_factor)
        b = int(b * b_factor)
        w = int(w * b_factor)
        """Set RGBW values for a fixture starting at the given channel"""
        if 1 <= start_channel <= 510:  # Need at least 3 channels
            self.dmx_frame[start_channel] = r
            self.dmx_frame[start_channel + 1] = g
            self.dmx_frame[start_channel + 2] = b
            self.dmx_frame[start_channel + 3] = w
            try:
                self.device.write_frame(self.dmx_frame)
                logger.info(f'RGBW fixture at channel {start_channel} set to R={r}, G={g}, B={b}, W={w}')
            except Exception as e:
                logger.error(f'Failed to set RGBW fixture: {e}')
        else:
            logger.error(f'Invalid start channel for RGBW fixture: {start_channel}')
