"""Root conftest for sc_navigator tests.

Placing this file here makes sc_navigator/ the pytest rootdir, so pytest does
not traverse up into the wingman-ai package tree (which requires the wingman
api module that main.py imports). The optimizer and build-script modules under
test have no host dependencies and import by bare name.
"""
