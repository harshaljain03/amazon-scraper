"""
Amazon Scraper Setup Configuration
"""

from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

with open("requirements.txt", "r", encoding="utf-8") as fh:
    requirements = [line.strip() for line in fh if line.strip() and not line.startswith("#")]

setup(
    name="amazon-scraper",
    version="1.0.0",
    author="Your Organization",
    author_email="contact@yourcompany.com",
    description="A comprehensive, production-ready Amazon product scraper",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/your-org/amazon-scraper",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Internet :: WWW/HTTP :: Browsers",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Topic :: System :: Monitoring",
    ],
    python_requires=">=3.11",
    install_requires=requirements,
    extras_require={
        "dev": [
            "pytest>=7.4.0",
            "pytest-asyncio>=0.21.0",
            "black>=23.12.0",
            "isort>=5.13.0",
            "mypy>=1.8.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "amazon-scraper=scraper.main:main",
            "amazon-scheduler=scheduler.scheduler:main",
        ],
    },
    include_package_data=True,
    package_data={
        "config": ["*.json", "*.yaml"],
        "monitoring": ["*.yml"],
    },
    project_urls={
        "Bug Reports": "https://github.com/your-org/amazon-scraper/issues",
        "Source": "https://github.com/your-org/amazon-scraper",
        "Documentation": "https://your-org.github.io/amazon-scraper/",
    },
)
