"""The root helper's jobs (BUILD 5.2, D27). These run as root, started only
through the package's units and its fixed polkit rule (or pkexec for `link`).
They never trust the user's input: requests are checked by owner and content.
"""
