# BDA - Benchmark Delta Analysis Tool

A Python tool for analyzing and visualizing differences between two Aider benchmark runs through an interactive dashboard.

[![PyPI version](https://badge.fury.io/py/cedarverse-bda.svg)](https://pypi.org/project/cedarverse-bda)
[![Python Versions](https://img.shields.io/pypi/pyversions/cedarverse-bda.svg)](https://pypi.org/project/cedarverse-bda/)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)

## Features

- Compares two benchmark run folders (raw or tar-bz2 archives)
- Interactive web dashboard built with Dash
- Detailed test-by-test comparison analysis
- Visualizes performance changes and differences

## Dashboard Features
- Test result comparison
- Performance metrics visualization
- Interactive data filtering and sorting
- Detailed test case analysis

![img.png](img.png)

![img_1.png](img_1.png)

![img_2.png](img_2.png)

![img_3.png](img_3.png)

## Installation

```bash
pipx install cedarverse-bda
```

## Usage

```bash
# Info on a single benchmark run
bda <run-path>

# Delta Analysis
bda <run1-path> <run2-path>

# Interactive dashboard
bda --dashboard <run-path>

```

## Development


```bash
# Install development dependencies
pip install -e .[dev]
```
