from setuptools import setup, find_packages

setup(
    name="umbra-pentest",
    version="1.0.0",
    description="Umbra Systems — Automated Penetration Testing Engine",
    packages=find_packages(),
    python_requires=">=3.10",
    entry_points={
        "console_scripts": [
            "pentest=war.pentest.cli:main",
        ],
    },
)
