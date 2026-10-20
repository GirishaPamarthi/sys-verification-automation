"""Shared framework for every MOSAIQ test suite in this project.

    from msq_framework import config, reporting

Modules are deliberately not imported here: `reporting` sets up Squish and patches
interops when imported, so each test imports it explicitly, before any interops import.
"""
