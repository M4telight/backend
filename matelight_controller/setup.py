from distutils.core import setup
from distutils.extension import Extension
import numpy
from Cython.Build import cythonize

setup(
   ext_modules=cythonize([
       Extension(
           "controller",
           sources=["c_controller.pyx"],
           include_dirs=[numpy.get_include()],
           language="c++",
       )
   ])
)