import logging

from tinkerforge.brick_esp32 import BrickESP32

from tinkerforge2mqtt.device_map import register_map_class
from tinkerforge2mqtt.device_map_utils.base import DeviceMapBase
from tinkerforge2mqtt.device_map_utils.utils import print_exception_decorator


logger = logging.getLogger(__name__)


@register_map_class()
class BrickESP32Mapper(DeviceMapBase):
    # https://www.tinkerforge.com/de/doc/Software/Bricks/HATZero_Brick_Python.html

    device_identifier = BrickESP32.DEVICE_IDENTIFIER

    def __init__(self, *, device: BrickESP32, **kwargs):
        self.device: BrickESP32 = device
        super().__init__(device=device, **kwargs)

    @print_exception_decorator
    def setup_sensors(self):
        super().setup_sensors()
        # Add any ESP32-specific sensors here if needed

    @print_exception_decorator
    def setup_callbacks(self):
        super().setup_callbacks()
        # Add any ESP32-specific callbacks here if needed
