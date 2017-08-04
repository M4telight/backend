import time
import math

from collections import namedtuple

from PIL import Image
from PIL import ImageDraw
from PIL import ImageFont
from datetime import datetime, timedelta

import socket
import struct
import threading
import zlib


Size = namedtuple('Size', ['height', 'width'])


class DataListener:
    def __init__(self,  controller, ip='', port=1337):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.setblocking(True)
        self.sock.bind(('0.0.0.0', port))

        self.controller = controller

        # rgb image without 4 bytes checksum
        self.frame_size = self.controller.image_width * self.controller.image_height * 3
        self.log = print
        self.ip = ip

    def close(self):
        self.sock.close()

    def get_data(self):
        return self.sock.recvfrom(self.frame_size + 4)

    def __iter__(self):
        while True:
            data, (addr, sport) = self.get_data()
            if addr != self.ip:
                # do not allow data form other hosts ;)
                continue

            if data is None:
                yield None, None

            if len(data) == self.frame_size + 4:
                (crc1,), crc2 = struct.unpack('!I', data[-4:]), zlib.crc32(data, 0),
                data = data[:-4]  # crop CRC
                # if crc1 and crc1 != crc2:  # crc1 zero-check for backward-compatibility
                #     self.log('Error receiving UDP frame: Invalid frame CRC checksum: Expected {}, got {}'.format(crc2, crc1))
                #     continue
            elif len(data) != self.frame_size:
                # self.log('Error receiving UDP frame: Invalid frame size: {}'.format(len(data)))
                continue
            yield 'udp:'+addr, data


class PauseFiller(threading.Thread):

    def __init__(self, motd, controller):
        super().__init__()
        self.motd = motd
        self.controller = controller
        self.stop = False
        self.font = ImageFont.truetype('assets/fonts/dotmat.ttf', 10)

    def get_pad_data(self, image, image_data, window_size):
        height, width, channels = image_data.shape

        height_padding = window_size.height - height
        padding_top = height_padding // 2
        padding_top_data = np.zeros((padding_top, image.width, channels))
        padding_bottom = math.ceil(height_padding / 2)
        padding_bottom_data = np.zeros((padding_bottom, image.width, channels))

        return padding_top_data, padding_bottom_data

    def display_text(self, image, slide_image=False):
        image_data = np.array(image)
        window_size = Size(height=self.controller.image_height, width=self.controller.image_width)
        window_position = 0

        padding_top, padding_bottom = self.get_pad_data(image, image_data, window_size)
        image_data = np.vstack((padding_top, image_data, padding_bottom))

        while True:
            if self.stop:
                break

            data = image_data.copy()[:, window_position:min(window_position + window_size[1], image.width), ...]
            height, width, channels = data.shape

            width_padding = np.zeros((window_size.height, window_size.width - width, channels))
            data = np.hstack((data, width_padding))

            self.controller.display(data)
            if slide_image:
                window_position += 1
                if window_position >= image.width:
                    window_position = 0
            time.sleep(1000 / 20 / 1000)

    def run(self):
        text_image = Image.new('RGB', self.font.getsize(self.motd))
        draw = ImageDraw.Draw(text_image)
        draw.fontmode = "1"
        draw.text((0, 0), self.motd, font=self.font, fill=(255, 255, 255))

        self.display_text(text_image, slide_image=True)


class IdleWatcher(threading.Thread):

    def __init__(self, idle_time):
        super().__init__()
        self.idle_time = idle_time

    def run(self):
        global pause_filler
        while True:
            time.sleep(timedelta(seconds=self.idle_time).total_seconds())
            time_now = datetime.utcnow()
            time_delta = (time_now - last_frame).total_seconds()

            if time_delta > self.idle_time and not pause_filler.is_alive():
                pause_filler = PauseFiller(args.motd, controller)
                pause_filler.start()


if __name__ == "__main__":
    import argparse
    import numpy as np
    from matelight_controller.python_controller import LEDController

    parser = argparse.ArgumentParser(description="Remote Display Server that shows already rendered images")
    parser.add_argument('config', help='path to config file for matelight')
    parser.add_argument('-p', '--port', type=int, default=1337, help='port to listen on')
    parser.add_argument('--idle-time', type=int, default=20, help='max. number of seconds matelight shall idle')
    parser.add_argument('--motd', default='Contribute on code.ilexlux.xyz!')
    parser.add_argument('--allowed-host', default='conrol.ilexlux.xyz', help='name of host to accept data from')

    args = parser.parse_args()

    ip_of_allowed_host = socket.gethostbyname(args.allowed_host)

    controller = LEDController(args.config)
    server = DataListener(controller, port=args.port, ip=ip_of_allowed_host)
    last_frame = datetime.utcnow()

    pause_filler = PauseFiller(args.motd, controller)
    pause_filler.start()

    idle_watcher = IdleWatcher(args.idle_time)
    idle_watcher.start()

    try:
        for _, frame in server:
            last_frame = datetime.utcnow()
            pause_filler.stop = True
            frame = np.fromstring(frame, dtype=np.uint8).reshape(controller.image_height, controller.image_width, 3)
            controller.display(frame)

    except KeyboardInterrupt:
        controller.shutdown()
        server.close()
