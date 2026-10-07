import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
os.environ.setdefault('XDG_CACHE_HOME','/workspace/.cache')
import pytest
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope='session')
def qapp():
    app=QApplication.instance() or QApplication([])
    app.setStyle('Fusion')
    return app
