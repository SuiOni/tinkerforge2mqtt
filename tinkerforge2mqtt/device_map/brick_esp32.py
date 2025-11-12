import logging

from tinkerforge.brick_esp32 import BrickESP32

from tinkerforge2mqtt.device_map import register_map_class
from tinkerforge2mqtt.device_map_utils.base import DeviceMapBase


logger = logging.getLogger(__name__)


@register_map_class()
class BrickESP32Mapper(DeviceMapBase):
    # https://www.tinkerforge.com/de/doc/Software/Bricks/HATZero_Brick_Python.html

    device_identifier = BrickESP32.DEVICE_IDENTIFIER

    def __init__(self, *, device: BrickESP32, **kwargs):
        self.device: BrickESP32 = device
        super().__init__(device=device, **kwargs)
