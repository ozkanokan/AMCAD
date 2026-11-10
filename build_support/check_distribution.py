"""Post-build structural checks, using only the builder's standard library."""
from pathlib import Path
import sys


def check(directory):
    directory=Path(directory)
    executable=directory/('AMCAD.exe' if sys.platform=='win32' else 'AMCAD')
    internal=directory/'_internal'
    required=[executable,internal/'library/components/generic.json']
    platform_plugin='qwindows.dll' if sys.platform=='win32' else 'libqcocoa.dylib' if sys.platform=='darwin' else 'libqoffscreen.so'
    missing=[str(path) for path in required if not path.is_file()]
    if not list(internal.rglob(platform_plugin)):missing.append(platform_plugin)
    if missing:raise SystemExit('Incomplete distribution: '+', '.join(missing))
    print('Distribution structure OK; platform plugin:',platform_plugin)


if __name__=='__main__':
    if len(sys.argv)!=2:raise SystemExit('Usage: check_distribution.py dist/AMCAD')
    check(sys.argv[1])
