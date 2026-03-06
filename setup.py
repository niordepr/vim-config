"""Setup configuration for the satellite broadcast distribution SDN controller."""

from setuptools import find_packages, setup

setup(
    name="satellite-sdn-controller",
    version="0.1.0",
    description="SDN controller for satellite broadcast distribution systems",
    packages=find_packages(),
    python_requires=">=3.10",
    install_requires=[
        "flask>=3.0.0,<4.0.0",
    ],
    extras_require={
        "dev": [
            "pytest>=7.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "satellite-sdn=satellite_sdn_controller.api:main",
        ],
    },
)
