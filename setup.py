from os import path

from setuptools import find_packages, setup

from monkey1shuffler.version import __version__

# Get the long description from the README file
# here = path.abspath( path.dirname( __file__ ) )
# with open( path.join( here, "DESCRIPTION.rst" ), encoding="utf-8" ) as f:
#    long_description = f.read()

setup(
    name="monkey1shuffler",
    version=__version__,
    description=("Secret of Monkey Island (EGA) Randomiser"),
    license="GPL-3.0",
    author="Scott Percival",
    author_email="code@moral.net.au",
    python_requires=">=3",
    install_requires=[
        "typing_extensions",
        "mrcrowbar >= 1.0.0rc1",
    ],
    extras_require={},
    packages=["monkey1shuffler"],
    entry_points={
        "console_scripts": [
            "monkey1shuffler = monkey1shuffler.cli:main",
        ],
    },
)
