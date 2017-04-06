import socket
import struct
import zlib


class DataListener:
    def __init__(self,  controller, ip='', port=1337):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.setblocking(True)
        self.sock.bind((ip, port))

        self.controller = controller

        # rgb image without 4 bytes checksum
        self.frame_size = self.controller.image_width * self.controller.image_height * 3
        self.log = print

    def close(self):
        self.sock.close()

    def get_data(self):
        return self.sock.recvfrom(self.frame_size + 4)

    def __iter__(self):
        while True:
            data, (addr, sport) = self.get_data()
            if data is None:
                yield None, None

            if len(data) == self.frame_size + 4:
                (crc1,), crc2 = struct.unpack('!I', data[-4:]), zlib.crc32(data, 0),
                data = data[:-4]  # crop CRC
                # if crc1 and crc1 != crc2:  # crc1 zero-check for backward-compatibility
                #     self.log('Error receiving UDP frame: Invalid frame CRC checksum: Expected {}, got {}'.format(crc2, crc1))
                #     continue
            elif len(data) != self.frame_size:
                self.log('Error receiving UDP frame: Invalid frame size: {}'.format(len(data)))
                continue
            yield 'udp:'+addr, data


if __name__ == "__main__":
    import argparse
    import numpy as np
    from matelight_controller.python_controller import LEDController

    parser = argparse.ArgumentParser(description="Remote Display Server that shows already rendered images")
    parser.add_argument('config', help='path to config file for matelight')
    parser.add_argument('-p', '--port', type=int, default=1337, help='port to listen on')

    args = parser.parse_args()

    controller = LEDController(args.config)
    server = DataListener(controller, port=args.port)

    try:
        for _, frame in server:
            frame = np.fromstring(frame, dtype=np.uint8).reshape(controller.image_height, controller.image_width, 3)
            controller.display(frame)

    except KeyboardInterrupt:
        controller.shutdown()
        server.close()
