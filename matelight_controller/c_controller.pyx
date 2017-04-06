try:
    import configparser
except ImportError:
    import ConfigParser as configparser

from cpython cimport array
import array

import numpy as np
cimport numpy as np

FLOAT_TYPE = np.float32
ctypedef np.float32_t FLOAT_TYPE_t

INT_TYPE = np.int32
ctypedef np.int32_t INT_TYPE_t

INT8_TYPE = np.uint8
ctypedef np.uint8_t INT8_TYPE_t


cdef class Crate:

    cdef int height
    cdef int width
    cdef int num_leds

    def __init__(self, height, width):
        pass

    def __cinit__(self, height, width):
        self.height = height
        self.width = width
        self.num_leds = height * width

    @property
    def crate_in_next_row(self):
        raise NotImplementedError("Please use subclass")

    @property
    def crate_in_next_column(self):
        raise NotImplementedError("Please use subclass")

    cdef reverse_every_even_column(self, np.ndarray[INT8_TYPE_t, ndim=3] data):
        cdef int width = data.shape[1]
        cdef int channels = data.shape[2]
        cdef np.ndarray[dtype=INT8_TYPE_t, ndim=3] column_data = np.empty((0, width, channels), dtype=INT8_TYPE)

        cdef int column_id
        cdef np.ndarray[dtype=INT8_TYPE_t, ndim=2] column

        for column_id in range(len(data)):
            column = data[column_id]
            if (column_id + 1) % 2 == 0:
                column = column[::-1]
            column_data = np.vstack((column_data, column[np.newaxis, ...]))
        return column_data

    cdef reverse_every_odd_column(self, np.ndarray[INT8_TYPE_t, ndim=3] data):
        cdef int width = data.shape[1]
        cdef int channels = data.shape[2]
        cdef np.ndarray[dtype=INT8_TYPE_t, ndim=3] column_data = np.empty((0, width, channels), dtype=INT8_TYPE)

        cdef int column_id
        cdef np.ndarray[dtype=INT8_TYPE_t, ndim=2] column

        for column_id in range(len(data)):
            column = data[column_id]
            if (column_id + 1) % 2 == 1:
                column = column[::-1]
            column_data = np.vstack((column_data, column[np.newaxis, ...]))
        return column_data

    cpdef transform_pixels(self, np.ndarray[INT8_TYPE_t, ndim=3] data):
        raise NotImplementedError("Please use subclass")

    def __str__(self):
        return self.__class__.__name__

cdef class BottomLeftCrate(Crate):
    @property
    def crate_in_next_row(self):
        return -1, BottomRightCrate

    @property
    def crate_in_next_column(self):
        return 1, TopLeftCrate

    cpdef transform_pixels(self, np.ndarray[INT8_TYPE_t, ndim=3] data):
        return self.reverse_every_odd_column(data)


cdef class BottomRightCrate(Crate):
    @property
    def crate_in_next_row(self):
        return -1, BottomLeftCrate

    @property
    def crate_in_next_column(self):
        return -1, TopRightCrate

    cpdef transform_pixels(self, np.ndarray[INT8_TYPE_t, ndim=3] data):
        return self.reverse_every_odd_column(data[::-1])


cdef class TopLeftCrate(Crate):
    @property
    def crate_in_next_row(self):
        return 1, TopRightCrate

    @property
    def crate_in_next_column(self):
        return 1, BottomLeftCrate

    cpdef transform_pixels(self, np.ndarray[INT8_TYPE_t, ndim=3] data):
        return self.reverse_every_even_column(data)


cdef class TopRightCrate(Crate):
    @property
    def crate_in_next_row(self):
        return 1, TopLeftCrate

    @property
    def crate_in_next_column(self):
        return -1, BottomRightCrate

    cpdef transform_pixels(self, np.ndarray[INT8_TYPE_t, ndim=3] data):
        return self.reverse_every_even_column(data[::-1])


NAME_TO_CRATE = {
    "bottomleftcrate": BottomLeftCrate,
    "bottomrightcrate": BottomRightCrate,
    "topleftcrate": TopLeftCrate,
    "toprightcrate": TopRightCrate,
}


cdef class LEDController:

    cdef int crate_rows
    cdef int crate_columns
    cdef int num_crates
    cdef int crate_width
    cdef int crate_height
    cdef int leds_per_crate
    cdef int image_height
    cdef int image_width
    # cdef array.array crates

    def __init__(self, config_file, device_name='/dev/spidev0.0'):
        pass

    def __cinit__(self, config_file, device_name='/dev/spidev0.0'):
        config = configparser.ConfigParser(allow_no_value=True)
        config.read(config_file)

        self.crate_rows = int(config["Layout"]["crate_rows"])
        self.crate_columns = int(config["Layout"]["crate_columns"])
        self.num_crates = self.crate_rows * self.crate_columns

        self.crate_width = int(config["Layout"]["crate_width"])
        self.crate_height = int(config["Layout"]["crate_height"])
        self.leds_per_crate = self.crate_width * self.crate_height

        self.image_width = self.crate_width * self.crate_columns
        self.image_height = self.crate_height * self.crate_rows

        crates = [crate.strip().lower() for crate in config["Crates"]["crates"].split(",")]
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

        self.device = open(self.device_name, "wb")
        self.device_name = device_name

    cpdef display(self, np.ndarray[INT8_TYPE_t, ndim=3] data):
        if data.shape[0] * data.shape[1] != self.num_crates * self.leds_per_crate:
            raise ValueError("Wrong datasize")

        # make data column major
        data = np.transpose(data, (1, 0, 2)).astype(np.uint8)
        cdef np.ndarray[INT8_TYPE_t, ndim=3] display_data = np.empty((0,), dtype=np.uint8)

        for (x, y), crate in self.crates:
            display_data = np.append(
                display_data,
                crate.transform_pixels(data[x * self.crate_width:(x + 1) * self.crate_width, y* self.crate_height:(y + 1) * self.crate_height]).flatten()
            )

        self.device.write(np.ascontiguousarray(display_data))
        self.device.flush()

    def turn_off_lights(self):
        cdef np.ndarray[INT8_TYPE_t, ndim=3] data = np.full((self.num_crates * self.leds_per_crate, 1, 3), 0, dtype=np.uint8)
        self.display(data)

    def shutdown(self):
        self.turn_off_lights()
        self.device.close()
