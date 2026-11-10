"""Frozen-only working-directory setup; application/library behavior is retained."""
import os
from pathlib import Path
import sys


def prepare_frozen_launch(argv):
    """Preserve caller-relative CLI project paths, then use writable Documents.

    Built-in resources use core.library.__file__, which PyInstaller locates
    under _internal. Editable libraries keep their existing per-user defaults.
    """
    if not getattr(sys,'frozen',False):return
    caller=Path.cwd()
    after_separator=False
    for index,arg in enumerate(argv[1:],1):
        if arg=='--':after_separator=True;continue
        if after_separator or not arg.startswith('-'):
            argv[index]=str((caller/arg).resolve());break
    from PySide6.QtCore import QStandardPaths
    override=os.environ.get('AMCAD_DOCUMENTS_DIR')
    if override:
        directory=Path(override).expanduser()
        if not directory.is_absolute():directory=caller/directory
    else:
        documents=QStandardPaths.writableLocation(QStandardPaths.DocumentsLocation)
        directory=(Path(documents) if documents else Path.home()/'Documents')/'AMCAD'
    directory.mkdir(parents=True,exist_ok=True)
    os.chdir(directory)
