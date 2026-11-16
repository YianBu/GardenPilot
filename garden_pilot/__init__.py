"""Standalone runner for the ok-ww weekly garden task.

The recognition assets under assets/templates come from ok-ww
(AGPL-3.0). This package reimplements the small part of that project
needed to play the weekly garden mode without depending on ok-script.
"""

from .features import TemplateSet
from .runner import GardenRunner

__all__ = ["TemplateSet", "GardenRunner"]
