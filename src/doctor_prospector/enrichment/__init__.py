"""Enrichment logic for Doctor Prospector.

Modules:
- physician_matcher: Match physicians to hospitals using NPPES + CMS data
"""

from .physician_matcher import PhysicianMatcher

__all__ = ["PhysicianMatcher"]
