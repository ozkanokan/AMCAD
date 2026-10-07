"""Run from the repository root: python -m app.main [project.amcad.json]."""
import argparse
import sys
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer
from ui.main_window import MainWindow


def main():
    parser = argparse.ArgumentParser(description='AMCAD Hydraulic Schematic Editor')
    parser.add_argument('project',nargs='?')
    parser.add_argument('--smoke',action='store_true',help='Launch, render and exit for environment validation')
    args=parser.parse_args()
    app=QApplication(sys.argv)
    app.setApplicationName('AMCAD')
    app.setStyle('Fusion')
    window=MainWindow()
    if args.project:
        try: window.load_path(args.project)
        except (OSError,ValueError,TypeError,KeyError) as error:
            print(f'Cannot load project: {error}',file=sys.stderr); return 1
    window.show()
    if args.smoke: QTimer.singleShot(300,app.quit)
    return app.exec()


if __name__=='__main__':
    raise SystemExit(main())
