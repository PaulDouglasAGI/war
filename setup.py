from setuptools import setup, find_packages

setup(
    name="umbra-pentest",
    version="1.0.0",
    description="Umbra Systems — Automated Penetration Testing Engine",
    packages=find_packages(),
    python_requires=">=3.10",
    extras_require={
        # Optional: enables headless-browser DOM-XSS execution confirmation
        # (phase 11). Chromium is pre-provisioned in the runtime image — install
        # only the Python package; do NOT run `playwright install`.
        "headless": ["playwright"],
    },
    entry_points={
        "console_scripts": [
            "pentest=war.pentest.cli:main",
        ],
    },
)
