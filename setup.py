"""Setup configuration for WaterBot package."""

from setuptools import find_packages, setup

setup(
    name="waterbot",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "python-dotenv>=1.0.0",
        "signalbot>=0.5.0",
        "schedule>=1.2.0",
        "RPi.GPIO>=0.7.1; platform_machine == 'armv6l' or "
        "platform_machine == 'armv7l'",
    ],
    python_requires=">=3.7",
    entry_points={
        "console_scripts": [
            "waterbot=waterbot.bot:main",
        ],
    },
    author="Your Name",
    author_email="your.email@example.com",
    description="A Signal bot to control GPIO pins on Raspberry Pi",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    keywords="raspberry pi, signal, bot, gpio",
    url="https://github.com/yourusername/waterbot",
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "License :: OSI Approved :: MIT License",
        "Operating System :: POSIX :: Linux",
    ],
)
