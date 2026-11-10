"""Packaging-only path/data isolation; native Windows acceptance is separate."""
from pathlib import Path
import sys
import pytest
from build_support.paths import prepare_frozen_launch
from build_support.check_distribution import check


def test_source_launch_does_not_change_paths_or_working_directory(tmp_path,monkeypatch):
    monkeypatch.chdir(tmp_path);monkeypatch.delattr(sys,'frozen',raising=False)
    args=['app.main','relative.json','--smoke']
    prepare_frozen_launch(args)
    assert Path.cwd()==tmp_path and args[1]=='relative.json'


@pytest.mark.parametrize('arguments',[
    ['AMCAD.exe','project with spaces.json','--smoke'],
    ['AMCAD.exe','--smoke','project with spaces.json'],
    ['AMCAD.exe','--','-project.json'],
])
def test_frozen_launch_preserves_caller_relative_project(tmp_path,monkeypatch,arguments):
    source=tmp_path/'protected installation';source.mkdir()
    documents=tmp_path/'User Documents'/'AMCAD'
    monkeypatch.chdir(source);monkeypatch.setattr(sys,'frozen',True,raising=False)
    monkeypatch.setenv('AMCAD_DOCUMENTS_DIR',str(documents))
    args=arguments.copy();original=next(a for a in arguments[1:] if not a.startswith('--'))
    # The '-' filename is valid after the explicit '--' separator.
    prepare_frozen_launch(args)
    assert str((source/original).resolve()) in args
    assert Path.cwd()==documents and documents.is_dir()
    assert not list(source.iterdir())


def test_default_frozen_working_directory_uses_documents_not_bundle(tmp_path,monkeypatch):
    from PySide6.QtCore import QStandardPaths
    installation=tmp_path/'install';installation.mkdir()
    user_documents=tmp_path/'Documents'
    monkeypatch.chdir(installation);monkeypatch.setattr(sys,'frozen',True,raising=False)
    monkeypatch.delenv('AMCAD_DOCUMENTS_DIR',raising=False)
    monkeypatch.setattr(QStandardPaths,'writableLocation',lambda location:str(user_documents))
    prepare_frozen_launch(['AMCAD.exe'])
    assert Path.cwd()==user_documents/'AMCAD' and not list(installation.iterdir())


def test_windows_default_libraries_stay_in_local_appdata(tmp_path,monkeypatch):
    from core.cavity_library import CavityLibrary
    from core.library import ComponentLibrary
    monkeypatch.setattr(sys,'platform','win32')
    monkeypatch.setenv('LOCALAPPDATA',str(tmp_path/'Local'))
    monkeypatch.delenv('AMCAD_COMPONENT_LIBRARY',raising=False)
    monkeypatch.delenv('AMCAD_CAVITY_LIBRARY',raising=False)
    assert CavityLibrary().directory==tmp_path/'Local/amcad/cavities'
    assert ComponentLibrary().directory==tmp_path/'Local/amcad/components'


def test_windows_distribution_check_requires_catalogue_and_platform_plugin(tmp_path,monkeypatch):
    monkeypatch.setattr(sys,'platform','win32')
    (tmp_path/'AMCAD.exe').write_bytes(b'placeholder for structural check')
    catalogue=tmp_path/'_internal/library/components/generic.json'
    catalogue.parent.mkdir(parents=True);catalogue.write_text('[]')
    with pytest.raises(SystemExit,match='qwindows.dll'):check(tmp_path)
    plugin=tmp_path/'_internal/PySide6/plugins/platforms/qwindows.dll'
    plugin.parent.mkdir(parents=True);plugin.write_bytes(b'placeholder')
    check(tmp_path)
