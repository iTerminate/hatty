# hatty — MIT License. See LICENSE file for details.
from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("hatty")
except PackageNotFoundError:  # running from a source tree without an installed dist
    __version__ = "0.0.0+dev"
