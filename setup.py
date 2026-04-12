"""Setup script for BDO Trainer"""

from pathlib import Path

from setuptools import find_packages, setup

this_directory = Path(__file__).parent
long_description = (this_directory / "README.md").read_text(encoding="utf-8")

setup(
    name="bdo-trainer",
    version="0.3.0",
    description="Transparent overlay combo trainer for Black Desert Online",
    long_description=long_description,
    long_description_content_type="text/markdown",
    packages=find_packages(),
    python_requires=">=3.9",
    install_requires=[
        "pyyaml>=6.0",
        "pystray>=0.19",
        "pillow>=10.0",
        "keyboard>=0.13",
        "pynput>=1.7",
        "requests>=2.28",
    ],
    extras_require={
        "dev": [
            "pytest>=7.0.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "bdo-trainer=main:main",
        ],
    },
    include_package_data=True,
    package_data={
        "": ["config/*.yaml", "config/classes/*.yaml"],
    },
    zip_safe=False,
)
