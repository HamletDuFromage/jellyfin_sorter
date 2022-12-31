#!/usr/bin/env python3

from bulk_jellyfin_sorter import FileSorter
from pathlib import Path
import argparse

if __name__ == '__main__':
        parser = argparse.ArgumentParser(description="Organize TV series")
        required = parser.add_argument_group('Required arguments')
        required.add_argument('-p', '--path', help='target directory', required=True)
        required.add_argument('-d', '--dryrun', help='target directory', action="store_true")
        args = parser.parse_args()

        path = Path(args.path)
        for p in path.iterdir():
            try:
                fs = FileSorter(p.resolve(), dry_run=args.dryrun)
                fs.identify_attributes()
                fs.rebuild_tree()
            except FileExistsError:
                print(f"{p.name} broke")
                pass