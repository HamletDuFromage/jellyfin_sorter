#!/usr/bin/env python3

import re
import argparse
import logging
from pathlib import Path


class Type:
    DEFAULT = 0
    VIDEO = 1
    MOVIE = 2
    SHOW = 3
    SHOW_SEASON = 4
    SHOW_EPISODE = 5
    SUBTITLE = 6
    FEATURETTE = 7
    MUSIC_ALBUM = 8
    MUSIC_SONG = 9


class FileInfo:
    def __init__(self, path):
        self.path = path
        self.VIDEO_EXTENSIONS = {r"mkv", r"mp4", r"avi", r"m4v"}
        self.MUSIC_EXTENSIONS = {r"flac", r"mp3", r"opus", r"wav", r"ogg"}

        self.regex_searches = set()
        self.regex_searches.add(r"(?i:s)(?i:eason.?)?(?P<season>\d{1,})")
        # self.regex_searches.add(r"(?i:e)(?i:pisode.?)?(?P<episode>\d{2,})")
        self.regex_searches.add(r"(?:(?i:part.?)|((?i:e)(?i:pisode.?)?))(?P<episode>\d{2,})")
        self.regex_searches.add(r"(?P<resolution>\d{3,4})p")
        self.regex_searches.add(r"(?:\.|\()(?P<year>\d{4})(?:\.|\))")
        self.regex_searches.add(r"\[(?P<tracker>\D+)\](\.\w+)?$")
        self.regex_searches.add(
            fr"\.(?P<extension>(?i:{'|'.join(self.VIDEO_EXTENSIONS.union(self.MUSIC_EXTENSIONS))})$)")
        self.regex_title = r"(?P<title>.*?)((" + ")|(".join(self.regex_searches) + "))"
        self.folder = self.path.is_dir()
        self.needs_subfolder = False
        self.tags = self.get_tags(path)
        self.tags["title"] = self.get_title()
        self.type = self.get_type()

    def file_children(self, path):
        if path.is_dir():
            return set(path.glob("*"))
        else:
            return {path}

    def get_title(self):
        title_search_result = re.search(self.regex_title, self.path.name)
        if title_search_result:
            title = title_search_result.groupdict().get("title")
        else:
            title = self.path.name
        title = title.replace(" ", ".").rstrip(".-_")
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

    def get_episodes(self, path) -> set:
        episodes = set()
        for p in self.file_children(path):
            if p.is_file():
                episode = self.get_tags(p).get("episode")
                if episode:
                    episodes.add(episode)
        return episodes

    def is_tv_episode(self) -> bool:
        episodes = self.get_episodes(self.path)
        if len(episodes) == 1:
            self.tags["episode"] = episodes.pop()
            if not self.tags.get("season"):
                self.tags["season"] = 1
            return True
        return False

    def get_seasons(self, path) -> set:
        seasons = set()
        for p in self.file_children(path):
            season = self.get_tags(p).get("season")
            if season:
                seasons.add(season)
        return seasons

    def is_tv_season(self) -> bool:
        if self.folder:
            seasons = self.get_seasons(self.path)
            episodes = self.get_episodes(self.path)
            if len(seasons) == 1:
                self.tags["season"] = seasons.pop()
                return True
            elif len(seasons) == 0 and len(episodes) > 1:
                self.tags["season"] = 1
                return True
        return False

    def is_tv_show(self) -> bool:
        return len(self.get_seasons(self.path)) > 1

    def is_featurette(self) -> bool:
        featurette_dirnames = {r"Behind The Scenes", r"Deleted Scenes",
                               r"Featurettes", r"Interviews", r"Scenes", r"Shorts", r"Trailers", r"Other"}
        featurette_pattern = "|".join(featurette_dirnames)
        return self.path.is_dir() and re.search(featurette_pattern, self.path.name, re.IGNORECASE)

    def is_movie(self) -> bool:
        return self.is_video()

    def is_video(self) -> bool:
        for p in self.file_children(self.path):
            if self.get_tags(p).get("extension") in self.VIDEO_EXTENSIONS:
                return True
        return False

    def get_songs_count(self, path) -> int:
        songs = 0
        if self.path.is_dir():
            for p in path.glob("*"):
                if self.get_tags(p).get("extension") in self.MUSIC_EXTENSIONS:
                    songs += 1
        elif self.get_tags(path).get("extension") in self.MUSIC_EXTENSIONS:
            songs += 1
        return songs

    def is_album(self) -> bool:
        return self.get_songs_count(self.path) > 1

    def is_song(self) -> bool:
        return self.get_songs_count(self.path) == 1

    def get_type(self):
        if self.is_featurette():
            return Type.FEATURETTE
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
        if self.is_album():
            return Type.MUSIC_ALBUM
        if self.is_song():
            return Type.MUSIC_SONG
        return Type.DEFAULT


class FileSorter:
    def __init__(self, path, library_path = None, dry_run=False):
        self.dry_run = dry_run
        self.path = Path(path)
        self.directory = Path(library_path) if library_path else self.path.parent
        logging.basicConfig(handlers=[logging.StreamHandler(),
                                      logging.FileHandler(self.directory.joinpath("jellyfin_sorter.log"))],
                            level=logging.INFO)

        if not self.path.exists():
            raise FileNotFoundError(error)
        if not self.path.is_absolute():
            raise FileNotFoundError("Provided path must be absolute")

        self.shows_path = self.directory.joinpath("Shows")
        self.movies_path = self.directory.joinpath("Movies")
        self.music_path = self.directory.joinpath("Music")
        media_paths = {self.shows_path, self.movies_path, self.music_path}

        if self.path in media_paths:
            raise FileExistsError(f"Hardlinker cannot be run on special directory {self.path.name}")

        for media_path in media_paths:
            self.create_folder(media_path)
        self.global_tags = {}

    def sort_file(self):
        self.build_tree(self.path)

    def create_folder(self, folder_path):
        try:
            if not self.dry_run:
                folder_path.mkdir(parents=True, exist_ok=False)
            logging.debug(f"Created {folder_path}")
        except FileExistsError:
            pass

    def hardlink_to_folder(self, source, destination_folder, needs_subfolder=False):
        if source != destination_folder:
            if not self.dry_run:
                if source.is_file():
                    self.create_folder(destination_folder)
                    if needs_subfolder:
                        destination_folder = destination_folder.joinpath(source.stem.replace(" ", "."))
                        self.create_folder(destination_folder)
                    destination_path = destination_folder.joinpath(source.name.replace(" ", "."))
                    try:
                        destination_path.hardlink_to(source)
                        logging.info(f"Hardlinked {source.name} to {destination_path.resolve()}")
                    except FileExistsError as error:
                        logging.error(error)
                else:
                    for f in source.iterdir():
                        self.hardlink_to_folder(f, destination_folder.joinpath(source.name))
        else:
            logging.error(f"Cannot hardlink {source.name} with itself!")

    def hardlink_in_folder(self, source, destination_folder):
        for f in source.iterdir():
            self.hardlink_to_folder(f, destination_folder)

    def create_symlink(self, source, destination):
        try:
            if not self.dry_run:
                source.symlink_to(destination, target_is_directory=True)
            logging.info(f"Created symlink {source.name} -> {destination.name}")
        except FileExistsError as error:
            logging.error(error)

    def update_tags(self, tags):
        for key, value in tags.items():
            if value:
                self.global_tags[key] = value

    def build_tree(self, path):
        file_info = FileInfo(path)
        logging.debug(f"{file_info.path} is of type {file_info.type}")
        self.update_tags(file_info.tags)

        if file_info.path.is_file() and file_info.type != Type.DEFAULT:
            file_info.needs_subfolder = True

        if file_info.type == Type.FEATURETTE:
            if self.global_tags.get("season"):  # Featurette from show
                featurette_path = self.shows_path.joinpath(file_info.tags.get("title"))
            else:  # Should never be reached
                featurette_path = self.movies_path.joinpath(file_info.path.name)
            self.hardlink_to_folder(file_info.path, featurette_path, file_info.needs_subfolder)

        elif file_info.type == Type.SHOW or file_info.type == Type.SHOW_SEASON:
            for subfolder in file_info.path.glob("*"):
                self.build_tree(subfolder)

        elif file_info.type == Type.SHOW_EPISODE:
            folder_path = self.shows_path.joinpath(
                self.global_tags.get("title"),
                f"season-{self.global_tags.get('season'):02}")
            self.hardlink_to_folder(file_info.path, folder_path, file_info.needs_subfolder)

        elif file_info.type == Type.MOVIE:
            self.hardlink_to_folder(file_info.path, self.movies_path, file_info.needs_subfolder)

        elif file_info.type in {Type.MUSIC_ALBUM, Type.MUSIC_SONG}:
            self.hardlink_to_folder(file_info.path, self.music_path, file_info.needs_subfolder)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Organize TV series")
    required = parser.add_argument_group('Required arguments')
    required.add_argument('-p', '--path', help='target file/directory', required=True)
    required.add_argument('-l', '--library', help='library path', required=False, default=None)
    required.add_argument('-d', '--dryrun', help='target directory', required=False, default=False)
    args = parser.parse_args()

    try:
        fs = FileSorter(args.path, args.library, args.dryrun)
    except (FileExistsError, FileNotFoundError) as error:
        logging.error(error)
    fs.sort_file()
