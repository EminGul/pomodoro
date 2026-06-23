from setuptools import setup, find_packages

setup(
    name="pomodoro",
    version="0.1.0",
    packages=find_packages(),
    install_requires=["click>=8.1"],
    entry_points={"console_scripts": ["pomodoro=pomodoro.cli:main"]},
)
