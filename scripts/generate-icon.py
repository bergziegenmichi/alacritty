from __future__ import annotations

import shutil
import sys
from enum import Enum
import os
from pathlib import Path

THEME_CACHE: dict[str, Theme] = {}


class SubdirType(Enum):
    Fixed = "fixed"
    Scalable = "scalable"


class Theme:
    path: Path = None
    index_file: Path = None
    parents: list[Theme] = None
    directories: list[ThemeSubdirectory] = None

    @staticmethod
    def get_theme_directory(theme_name: str) -> Path:
        icon_theme_directories = [
            Path.home() / ".local/share/icons",
            Path("/usr/share/icons")
        ]
        for icon_theme_directory in icon_theme_directories:
            theme_directory = icon_theme_directory / theme_name
            if theme_directory.is_dir():
                return theme_directory

    @staticmethod
    def from_theme_name(theme_name: str) -> Theme:
        return Theme.check_cache_before_creation(Theme.get_theme_directory(theme_name))

    @staticmethod
    def check_cache_before_creation(theme_directory: Path) -> Theme:
        if str(theme_directory) in THEME_CACHE.keys():
            return THEME_CACHE[str(theme_directory)]
        else:
            return Theme(theme_directory)

    def __init__(self, theme_directory: Path):
        self.path = theme_directory
        self.index_file = theme_directory / "index.theme"

        with open(self.index_file, "r") as f:
            for line in f:
                line = line.strip()
                if line.startswith("[") and line != "[Icon Theme]":
                    break

                split_line = line.split("=")
                if len(split_line) == 2:
                    k: str = split_line[0]
                    v: str = split_line[1]
                    vs: list[str] = v.split(",")
                    if k == "Inherits":
                        self.parents = [Theme.from_theme_name(theme_name) for theme_name in vs]
                    if k == "Directories":
                        self.directories = [ThemeSubdirectory(Path(relpath), self) for relpath in vs]

    def has_parents(self) -> bool:
        return self.parents is not None and len(self.parents)


class ThemeSubdirectory:
    relpath: Path = None
    theme: Theme = None
    type: SubdirType = None
    size: int = None
    min_size: int = None
    max_size: int = None
    scale: int = None

    def __init__(self, relpath: Path, theme: Theme):
        self.relpath = relpath
        self.theme = theme

        read: bool = False

        with open(theme.index_file, "r") as f:
            for line in f:
                line = line.strip()
                if read:
                    if line.startswith("["):
                        break

                    split_line = line.split("=")
                    if len(split_line) == 2:
                        k, v = split_line
                        if k == "Type":
                            if v == "Fixed":
                                self.type = SubdirType.Fixed
                            elif v == "Scalable":
                                self.type = SubdirType.Scalable
                        elif k == "Size":
                            self.size = int(v)
                        elif k == "MinSize":
                            self.min_size = int(v)
                        elif k == "MaxSize":
                            self.max_size = int(v)
                        elif k == "Scale":
                            self.scale = int(v)

                if line == f"[{str(relpath)}]":
                    read = True

        if self.scale is None:
            self.scale = 1

    def full_path(self) -> Path:
        return self.theme.path / self.relpath


def find_icon(theme_name: str, icon: str, size: int, scale: str):
    filename = find_icon_helper(icon, size, scale,
                                Theme.check_cache_before_creation(Theme.get_theme_directory(theme_name)))
    if filename is not None:
        return filename

    filename = find_icon_helper(icon, size, scale,
                                Theme.check_cache_before_creation(Theme.get_theme_directory("hicolor")))
    if filename is not None:
        return filename


def find_icon_helper(icon: str, size: int, scale: str, theme: Theme):
    filename = lookup_icon(icon, size, scale, theme)
    if filename is not None:
        return filename

    if theme.has_parents():
        for parent in theme.parents:
            filename = find_icon_helper(icon, size, scale, parent)
            if filename is not None:
                return filename

    return None


def lookup_icon(iconname: str, size: int, scale: str, theme: Theme):
    for subdir in theme.directories:
        for extension in ["png", "svg", "xpm"]:
            if directory_matches_size(subdir, size, scale):
                filename = f"{subdir.full_path()}/{iconname}.{extension}"
                if os.path.exists(filename):
                    return filename

    minimal_size = sys.maxsize
    closest_filename: str = ""
    for subdir in theme.directories:
        for extension in ["png", "svg", "xpm"]:
            filename = f"{subdir.full_path()}/{iconname}.{extension}"
            if os.path.exists(filename) and directory_size_distance(subdir, size, scale) < minimal_size:
                closest_filename = filename
                minimal_size = directory_size_distance(subdir, size, scale)

    if closest_filename is not None:
        return closest_filename

    return None


def directory_matches_size(subdir: ThemeSubdirectory, icon_size: int, icon_scale: str):
    if subdir.scale != icon_scale:
        return False
    if subdir.type is SubdirType.Fixed:
        return subdir.size == icon_size
    elif subdir.type is SubdirType.Scalable:
        return subdir.min_size <= icon_size <= subdir.max_size


def directory_size_distance(subdir, icon_size, icon_scale):
    icon_dimension = icon_size * icon_scale

    if subdir.type == SubdirType.Fixed:
        return abs(subdir.size * subdir.scale - icon_dimension)

    elif subdir.type == SubdirType.Scalable:
        if icon_dimension < subdir.min_size * subdir.scale:
            return subdir.min_size * subdir.scale - icon_dimension
        elif icon_dimension > subdir.max_size * subdir.scale:
            return icon_dimension - subdir.max_size * subdir.scale
        return 0

    else:
        return sys.maxsize


def get_theme_name() -> str:
    theme: str = ""
    with open(os.path.expanduser("~/.config/kdeglobals"), "r") as f:
        for line in f:
            if line.strip() == "[Icons]":
                theme = next(f, "").strip().split("=")[1]
        f.close()
    return theme


def convert_svg_to_png(input_path: Path, output_path: Path, resolution: int):
    os.system(f"inkscape -w {resolution} -h {resolution} {input_path} -o {output_path}")


def generate_icon(output_path: Path):
    theme_name = get_theme_name()
    icon_path = Path(find_icon(theme_name, "utilities-terminal", 64, 1))
    if icon_path.suffix == ".svg":
        convert_svg_to_png(input_path=icon_path, output_path=output_path, resolution=64)
    elif icon_path.suffix == ".png":
        shutil.copyfile(str(icon_path.absolute()), str(output_path.absolute()))
    else:
        print("unknown file type")


if __name__ == "__main__":
    os.system("touch /home/michael/ichbinda")
    os.system("echo \"1\" > /home/michael/ichbinda")
    image_path = Path(sys.argv[1])
    os.system(f"echo \"{image_path}\" >> /home/michael/ichbinda")
    current_path = Path(__file__)
    full_path = current_path.parent / image_path
    generate_icon(full_path)
