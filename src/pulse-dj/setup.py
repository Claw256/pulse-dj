"""Setup script for pulse-dj package"""

from setuptools import setup, find_packages

setup(
    name="pulse-dj",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "numpy>=1.24.0",
        "zeroconf>=0.115.0",
        "aiolifx>=0.8.9",
        "sounddevice>=0.4.6"
    ]
)
