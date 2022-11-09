import re
import argparse
from pathlib import Path


class Type:
    DEFAULT = 0
    VIDEO = 1
    MOVIE = 2
    SHOW = 3
    SHOW_SEASON = 4
    SHOW_EPISODE = 5
    SUBTITLE = 6


class FileInfo:
    def __init__(self, path):
        self.path = path
        VIDEO_EXTENSIONS = {r"mkv", r"mp4", r"avi", r"m4v"}

        self.regex_searches = set()
        self.regex_searches.add(r"(?i:s)(?i:eason.?)?(?P<season>\d{1,})")
        self.regex_searches.add(r"(?i:e)(?i:pisode.?)?(?P<episode>\d{2,})")
        self.regex_searches.add(r"(?P<resolution>\d{3,4})p")
        self.regex_searches.add(r"(?:\.|\()(?P<year>\d{4})(?:\.|\))")
        self.regex_searches.add(r"\[(?P<tracker>\D+)\](\.\w+)?$")
        self.regex_searches.add(fr"\.(?P<extension>(?i:{'|'.join(VIDEO_EXTENSIONS)})$)")
        self.regex_title = r"(?P<title>.*?)((" + ")|(".join(self.regex_searches) + "))"
        self.folder = self.path.is_dir()
        self.tags = self.get_tags(path)
        self.tags["title"] = self.get_title()
        self.type = self.get_type()

    def get_title(self):
        title_search_result = re.search(self.regex_title, self.path.name)
        if title_search_result:
            title = title_search_result.groupdict().get("title")
        else:
            title = self.path.name
        title = title.replace(" ", ".").rstrip(".")
        return ".".join([w.capitalize() for w in title.split(".")])

    def get_tags(self, path):
        tags = {}
        for regex_search in self.regex_searches:
            search_result = re.search(regex_search, path.name)
            if search_result:
                tags |= search_result.groupdict()
        for int_tag in {"episode", "season", "year", "resolution"}:
            if int_tag in tags:
                tags[int_tag] = int(tags.get(int_tag))
        return tags

    def is_tv_show(self) -> bool:
        seasons = set()
        for p in self.path.rglob("*"):
            season = self.get_tags(p).get("season")
            if season:
                seasons.add(int(season))
        return len(seasons) > 1

    def is_tv_season(self) -> bool:
        seasons = set()
        for p in self.path.rglob("*"):
            season = self.get_tags(p).get("season")
            if season:
                seasons.add(int(season))
        if len(seasons) == 1:
            self.tags["season"] = seasons.pop()
            return True
        return False

    def is_tv_episode(self) -> bool:
        if self.folder:
            episodes = set()
            for p in self.path.glob("*"):
                if p.is_file():
                    episode = self.get_tags(p).get("episode")
                    if episode:
                        episodes.add(int(episode))
            if len(episodes) == 1:
                self.tags["episode"] = episodes.pop()
                return True
            return False
        else:
            return bool(self.tags.get("episode"))

    def is_video(self) -> bool:
        for p in self.path.rglob("*"):
            if self.get_tags(p).get("extension"):
                return True
        return bool(self.get_tags(self.path).get("extension"))

    def is_movie(self) -> bool:
        return self.is_video()

    def get_type(self):
        if self.is_tv_episode():
            return Type.SHOW_EPISODE
        if self.is_tv_season():
            return Type.SHOW_SEASON
        if self.is_tv_show():
            return Type.SHOW
        if self.is_movie():
            return Type.MOVIE
        if self.path.suffix == ".srt":
            return Type.SUBTITLE
        return Type.DEFAULT


class FileSorter:
    def __init__(self, path, dry_run=False):
        self.dry_run = dry_run
        self.path = Path(path)
        if not self.path.exists():
            raise FileNotFoundError(f"{self.path} was not found")
        if not self.path.is_absolute():
            raise FileNotFoundError("Provided path must be absolute")
        self.directory = self.path.parent

        self.shows_path = self.directory.joinpath("Shows")
        self.movies_path = self.directory.joinpath("Movies")

        if self.path in {self.shows_path, self.movies_path}:
            raise FileExistsError(f"Renamer cannot be run on special directory {self.path.name}")

        self.create_folder(self.shows_path)
        self.create_folder(self.movies_path)
        self.global_tags = {}

    def sort_file(self):
        self.build_tree(self.path)

    def create_folder(self, folder_path):
        try:
            if not self.dry_run:
                folder_path.mkdir(parents=True, exist_ok=False)
            print(f"Created {folder_path}")
        except FileExistsError:
            pass

    def move_to_folder(self, source, destination_folder):
        if not self.dry_run:
            self.create_folder(destination_folder)
            source.rename(destination_folder.joinpath(source.name))
        print(f"Moved {source.name} to {destination_folder.resolve()}")

    def merge_folders(self, source, destination):
        if source != destination:
            for f in source.iterdir():
                if not destination.exists() or f.is_file():
                    self.move_to_folder(f, destination)
                else:
                    self.merge_folders(f, destination.joinpath(f.name))
            if not self.dry_run:
                source.rmdir()
        else:
            print(f"Cannot merge {source.name} with itself!")

    def create_symlink(self, source, destination):
        try:
            if not self.dry_run:
                source.symlink_to(destination, target_is_directory=True)
            print(f"Created symlink {source.name} -> {destination.name}")
        except FileExistsError:
            print(f"Couldn't create symlink {source.name} -> {destination.name}")

    def update_tags(self, tags):
        for key, value in tags.items():
            if value:
                self.global_tags[key] = value

    def build_tree(self, path):
        file_info = FileInfo(path)
        print(f"{file_info.path} is of type {file_info.type}")
        self.update_tags(file_info.tags)

        if " " in file_info.path.name:
            dotted_path = file_info.path.parent.joinpath(file_info.path.name.replace(" ", "."))
            if not self.dry_run:
                file_info.path = file_info.path.rename(dotted_path)
            else:
                file_info.path = dotted_path

        if not file_info.folder and file_info.type != Type.DEFAULT:
            folder_path = file_info.path.parent.joinpath(file_info.path.stem)
            self.move_to_folder(file_info.path, folder_path)
            file_info.path = folder_path
            file_info.folder = True

        if file_info.type == Type.SHOW or file_info.type == Type.SHOW_SEASON:
            for subfolder in file_info.path.glob("*"):
                self.build_tree(subfolder)

        elif file_info.type == Type.SHOW_EPISODE:
            folder_path = self.shows_path.joinpath(
                self.global_tags.get("title"),
                f"season-{self.global_tags.get('season'):02}")
            self.move_to_folder(file_info.path, folder_path)

        elif file_info.type == Type.MOVIE:
            self.merge_folders(file_info.path, self.movies_path.joinpath(file_info.path.name))

        if not self.dry_run:
            if file_info.path.suffix == ".txt":
                file_info.path.unlink()
            try:
                file_info.path.rmdir()
            except OSError:
                pass


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Organize TV series")
    required = parser.add_argument_group('Required arguments')
    required.add_argument('-p', '--path', help='target directory', required=True)
    required.add_argument('-d', '--dryrun', help='target directory', required=False)
    args = parser.parse_args()

    fs = FileSorter(args.path, args.dryrun)
    fs.sort_file()
