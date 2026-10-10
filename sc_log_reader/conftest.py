"""Root conftest for log_donor tests.

Placing this file here makes sc_log_reader/ the pytest rootdir,
preventing pytest from traversing up into the wingman-ai package
tree (which requires the wingman api module to be installed).
"""
