"""Case-history subsystem.

Import the FastAPI router explicitly from :mod:`app.history.router`.  Keeping
this package initializer side-effect free also lets the demo CLI run without
loading the JWT/router stack first.
"""
