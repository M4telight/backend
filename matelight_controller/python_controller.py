import configparser
import time

import numpy as np
from scipy.misc import imresize


class Crate(object):
    def __init__(self, height=4, width=5):
        self.height = height
        self.width = width
        self.num_leds = height * width

    def check_bounds(self, data):
        # assert data.shape[0] == self.width
        # assert data.shape[1] == self.height
        pass

    @property
    def crate_in_next_row(self):
        raise NotImplementedError("Please use subclass")

    @property
    def crate_in_next_column(self):
        raise NotImplementedError("Please use subclass")   

    def reverse_every_even_column(self, data):
        column_data = np.empty((0, ) + data.shape[1:], dtype=np.uint8)
        for column_id, column in enumerate(data, start=1):
            if column_id % 2 == 0:
                column = column[::-1]
            column_data = np.vstack((column_data, column[np.newaxis, ...]))
        return column_data

    def reverse_every_odd_column(self, data):
        column_data = np.empty((0, ) + data.shape[1:], dtype=np.uint8)
        for column_id, column in enumerate(data, start=1):
            if column_id % 2 == 1:
                column = column[::-1]
            column_data = np.vstack((column_data, column[np.newaxis, ...]))
        return column_data

    def transform_pixels(self, data):
        raise NotImplementedError("Please use subclass of Crate")

    def __str__(self):
        return self.__class__.__name__


class BottomLeftCrate(Crate):
    @property
    def crate_in_next_row(self):
        return -1, BottomRightCrate

    @property
    def crate_in_next_column(self):
        return 1, TopLeftCrate

    def transform_pixels(self, data):
        self.check_bounds(data)
        return self.reverse_every_odd_column(data)


class BottomRightCrate(Crate):
    @property
    def crate_in_next_row(self):
        return -1, BottomLeftCrate

    @property
    def crate_in_next_column(self):
        return -1, TopRightCrate

    def transform_pixels(self, data):
        self.check_bounds(data)
        return self.reverse_every_odd_column(data[::-1])


class TopLeftCrate(Crate):
    @property
    def crate_in_next_row(self):
        return 1, TopRightCrate

    @property
    def crate_in_next_column(self):
        return 1, BottomLeftCrate

    def transform_pixels(self, data):
        self.check_bounds(data)
        return self.reverse_every_even_column(data)


class TopRightCrate(Crate):
    @property
    def crate_in_next_row(self):
        return 1, TopLeftCrate

    @property
    def crate_in_next_column(self):
        return -1, BottomRightCrate

    def transform_pixels(self, data):
        self.check_bounds(data)
        return self.reverse_every_even_column(data[::-1])

NAME_TO_CRATE = {
    "bottomleftcrate": BottomLeftCrate,
    "bottomrightcrate": BottomRightCrate,
    "topleftcrate": TopLeftCrate,
    "toprightcrate": TopRightCrate,
}


class LEDController(object):

    def __init__(self, config_file, device_name="/dev/spidev0.0"):
        self.config = configparser.ConfigParser(allow_no_value=True)
        self.config.read(config_file)

        self.crate_rows = int(self.config["Layout"]["crate_rows"])
        self.crate_columns = int(self.config["Layout"]["crate_columns"])
        self.num_crates = self.crate_rows * self.crate_columns

        self.crate_width = int(self.config["Layout"]["crate_width"])
        self.crate_height = int(self.config["Layout"]["crate_height"])
        self.leds_per_crate = self.crate_width * self.crate_height

        self.image_width = self.crate_width * self.crate_columns
        self.image_height = self.crate_height * self.crate_rows

        crates = [crate.strip().lower() for crate in self.config["Crates"]["crates"].split(",")]
        self.crates = [((0,0), NAME_TO_CRATE[crates[0]](self.crate_height, self.crate_width))]
        for crate in crates[1:]:
            crate_type = NAME_TO_CRATE[crate]
            last_position, last_crate = self.crates[-1]
            row_displace, next_row_crate = last_crate.crate_in_next_row
            column_displace, next_column_crate = last_crate.crate_in_next_column

            if crate_type == next_row_crate:
                self.crates.append(((last_position[0], last_position[1] + row_displace), crate_type(width=self.crate_width, height=self.crate_height)))
            elif crate_type == next_column_crate:
                self.crates.append(((last_position[0] + column_displace, last_position[1]), crate_type(width=self.crate_width, height=self.crate_height)))
            else:
                raise ValueError("Your specification of crates seems not to be plausible! Please check that!")

        # adjust crate indices so that top left crate has index (0,0)
        min_x = min(self.crates, key=lambda x: x[0][0])[0][0]
        min_y = min(self.crates, key=lambda x: x[0][1])[0][1]
        self.crates = [((x + abs(min_x), y), crate) for (x, y), crate in self.crates]
        self.crates = [((x, y + abs(min_y)), crate) for (x, y), crate in self.crates]

        print(self.crates)

        self.device = None
        self.device_name = device_name

    def display(self, data):
        if len(data.shape) != 3 or data.shape[0] * data.shape[1] != self.num_crates * self.leds_per_crate:
            print(data.shape)
            data = imresize(data, (self.image_height, self.image_width, 3))
        if self.device is None:
            self.device = open(self.device_name, "wb")
        # make data column major
        data = np.transpose(data, (1, 0, 2)).astype(np.uint8)
        display_data = np.empty((0,), dtype=np.uint8)
        for (x, y), crate in self.crates:
            display_data = np.append(
                display_data,
                crate.transform_pixels(data[x * self.crate_width:(x + 1) * self.crate_width, y* self.crate_height:(y + 1) * self.crate_height]).flatten()
            )
        self.device.write(np.ascontiguousarray(display_data))
        self.device.flush()

    def turn_off_lights(self):
        data = np.full((self.num_crates * self.leds_per_crate, 1, 3), 0, dtype=np.uint8)
        self.display(data)

    def shutdown(self):
        self.turn_off_lights()
        self.device.close()


if __name__ == "__main__":
    import argparse
    import random

    parser = argparse.ArgumentParser(description="test script for LED Controller Class")
    parser.add_argument("config", help="path to config file, describing matelight layout")
    parser.add_argument("-n", dest="num_leds", action="store", type=int, help="number of LEDS", default=50)
    parser.add_argument("-s", dest="sleep_time", action="store", type=int, help="time before refresh in ms", default=10)

    args = parser.parse_args()

    data = np.full((12, 15, 3), 0, dtype=np.uint8)
    colors = np.vectorize(lambda x: random.randint(0, 255))
    controller = LEDController(args.config)
    try:
        while True:
            controller.display(colors(data))
            time.sleep(args.sleep_time / 1000)
    except KeyboardInterrupt:
        controller.shutdown()
