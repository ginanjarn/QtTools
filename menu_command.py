"""QT Tools"""

import os
import subprocess
import threading

from dataclasses import dataclass, asdict
from abc import ABC, abstractmethod
from enum import Enum
from pathlib import Path
from typing import List

from string import Template

import sublime
import sublime_plugin


def get_project_folder(path: str) -> str:
    folders = sublime.active_window().folders()

    candidates = [folder for folder in folders if path.startswith(folder)]
    if candidates:
        return max(candidates)

    raise ValueError("unable find project folders")


class QttoolsOpenDesignerCommand(sublime_plugin.TextCommand):
    def run(self, edit: sublime.Edit):
        file_path = self.view.file_name()
        try:
            subprocess.Popen(["designer", file_path])

        except FileNotFoundError:
            message = "Unable find Qt 'designer'.\n" "Set 'designer' directory in PATH."
            sublime.error_message(message)

    def is_visible(self):
        return self.view.match_selector(0, "text.qt.ui")


class Canceled(Exception):
    """"""


CURRENT_FILE_DIRECTORY = Path(__file__).parent

# QObject classes listed in '$cwd/resources/qobjects.txt'
qobjecs_path = CURRENT_FILE_DIRECTORY.joinpath("resource", "qobjects.txt")
QOBJECT_CLASSES = qobjecs_path.read_text().splitlines()


def text_input(caption: str, initial_text: str = "") -> str:
    event = threading.Event()
    temp = ""

    def on_done(text):
        nonlocal temp
        temp = text
        event.set()

    def on_cancel():
        event.set()

    sublime.active_window().show_input_panel(
        caption=caption,
        initial_text=initial_text,
        on_done=on_done,
        on_cancel=on_cancel,
        on_change=None,
    )

    # wait until done or canceled
    event.wait()
    return temp


def choice_input(
    choices: List[str], placeholder: str = "", *, selected_index: int = -1, **kwargs
) -> str:
    temp = ""
    event = threading.Event()

    def on_select(index):
        nonlocal temp
        # on cancel, index == -1
        if index >= 0:
            temp = choices[index]

        event.set()

    sublime.active_window().show_quick_panel(
        choices,
        on_select=on_select,
        placeholder=placeholder,
        selected_index=selected_index,
        **kwargs,
    )

    # wait until selected or canceled
    event.wait()
    return temp


def yesno_input(title: str) -> bool:
    opt = ["Yes", "No"]
    result = choice_input(opt, title, selected_index=0)
    return result == opt[0]


@dataclass
class Config:
    class_name: str
    baseclass_name: str = ""
    source: str = ""
    header: str = ""
    include_guard: str = ""

    def __post_init__(self):
        if not self.class_name.isidentifier():
            raise ValueError(f"Invalid class name {self.class_name!r}")

        self.source = self.class_name + ".cpp"
        self.header = self.class_name + ".h"
        self.include_guard = self.class_name.upper() + "_H"


def write_snippet(file_path: Path, text: str, config: Config, /):
    template = Template(text)
    new_text = template.substitute(asdict(config))
    file_path.write_text(new_text)


def get_template(file_name: str) -> str:
    path = CURRENT_FILE_DIRECTORY.joinpath("template", file_name)
    return path.read_text()


class AbstractGenerator(ABC):
    """Abstract snippet generator"""

    @abstractmethod
    def configure(self):
        """configure parameters"""

    @abstractmethod
    def generate(self):
        """generate snippet"""


class PlainClass(AbstractGenerator):
    source_template = "sources/class_plain.txt"
    header_template = "headers/class_plain.txt"

    def __init__(self, base_path: Path):
        self.base_path = Path(base_path)
        self.config: Config = None

    def configure(self):
        class_name = text_input("Class name")
        if not class_name:
            raise Canceled("class_name undefined")

        self.config = Config(class_name)

    def generate(self):
        source_path = self.base_path.joinpath(self.config.source)
        write_snippet(source_path, get_template(self.source_template), self.config)

        header_path = self.base_path.joinpath(self.config.header)
        write_snippet(header_path, get_template(self.header_template), self.config)


class HeaderClass(AbstractGenerator):
    header_template = "headers/class_plainheader.txt"

    def __init__(self, base_path: Path):
        self.base_path = Path(base_path)
        self.config: Config = None

    def configure(self):
        class_name = text_input("Class name")
        if not class_name:
            raise Canceled("class_name undefined")

        self.config = Config(class_name)

    def generate(self):
        header_path = self.base_path.joinpath(self.config.header)
        write_snippet(header_path, get_template(self.header_template), self.config)


class InterfaceClass(AbstractGenerator):
    header_template = "headers/class_interface.txt"

    def __init__(self, base_path: Path):
        self.base_path = Path(base_path)
        self.config: Config = None

    def configure(self):
        class_name = text_input("Class name")
        if not class_name:
            raise Canceled("class_name undefined")

        self.config = Config(class_name)

    def generate(self):
        header_path = self.base_path.joinpath(self.config.header)
        write_snippet(header_path, get_template(self.header_template), self.config)


class QObjectClass(AbstractGenerator):
    source_template = "sources/class_qobject.txt"
    header_template = "headers/class_qobject.txt"

    def __init__(self, base_path: Path):
        self.base_path = Path(base_path)
        self.config: Config = None

    def configure(self):
        classes = QOBJECT_CLASSES
        baseclass_name = choice_input(classes, "Base Class", selected_index=0)
        if not baseclass_name:
            raise Canceled("baseclass_name undefined")

        class_name = text_input("Class name", initial_text=baseclass_name.lstrip("Q"))
        if not class_name:
            raise Canceled("class_name undefined")

        self.config = Config(class_name, baseclass_name)

    def generate(self):
        source_path = self.base_path.joinpath(self.config.source)
        write_snippet(source_path, get_template(self.source_template), self.config)

        header_path = self.base_path.joinpath(self.config.header)
        write_snippet(header_path, get_template(self.header_template), self.config)


class UiClass(AbstractGenerator):
    source_template = "sources/class_ui.txt"
    header_template = "headers/class_ui.txt"

    def __init__(self, base_path: Path):
        self.base_path = Path(base_path)
        self.config: Config = None

        self.create_class = False

    def configure(self):
        ui_classes = ["QWidget", "QDialog", "QMainWindow"]
        baseclass_name = choice_input(ui_classes, "Base Class", selected_index=0)
        if not baseclass_name:
            raise Canceled("baseclass_name undefined")

        self.create_class = yesno_input("Create Implementation Class")

        class_name = text_input("Class name", initial_text=baseclass_name.lstrip("Q"))
        if not class_name:
            raise Canceled("class_name undefined")

        self.config = Config(class_name, baseclass_name)

    def generate(self):
        ui_path = self.base_path.joinpath(self.config.class_name + ".ui")
        baseclass_name = self.config.baseclass_name.lower()
        ui_template = f"ui/form_{baseclass_name}.txt"
        write_snippet(ui_path, get_template(ui_template), self.config)

        if self.create_class:
            source_path = self.base_path.joinpath(self.config.source)
            write_snippet(source_path, get_template(self.source_template), self.config)

            header_path = self.base_path.joinpath(self.config.header)
            write_snippet(header_path, get_template(self.header_template), self.config)


class ClassKind(Enum):
    PLAIN = PlainClass
    QOBJECT = QObjectClass
    UI = UiClass
    INTERFACE = InterfaceClass
    HEADER = HeaderClass


class QttoolsCreateClassCommand(sublime_plugin.WindowCommand):
    """"""

    def run(self, kind: str, dirs: "list[str]"):
        try:
            kind = ClassKind[kind]
        except KeyError:
            print("Error! Valid 'kind' argument:", [c.name for c in ClassKind])
            return

        if not dirs:
            print("Error! Argument 'dirs' must assiged.")
            return

        threading.Thread(target=self.run_task, args=(kind, dirs)).start()

    def run_task(self, cls_kind: ClassKind, dirs: "list[str]"):

        base_path = Path(dirs[0])
        constructor = cls_kind.value
        generator: AbstractGenerator = constructor(base_path)

        try:
            generator.configure()
        except Canceled as err:
            print(err)
        else:
            generator.generate()

    def is_visible(self, kind: "ClassKind", dirs: "list[str]"):
        return len(dirs) == 1


class QttoolsTouchCommand(sublime_plugin.WindowCommand):
    """"""

    def run(self, dirs: "list[str]"):
        if not dirs:
            return

        threading.Thread(target=self.run_task, args=(dirs,)).start()

    def run_task(self, dirs: "list[str]"):

        prefix_path = dirs[0]
        project_folder = get_project_folder(prefix_path)
        rel_prefix_path = f"{prefix_path[len(project_folder) + 1 :]}{os.sep}"

        input_path = text_input("File name", initial_text=rel_prefix_path)
        if not input_path or input_path == rel_prefix_path:
            return

        file_path = Path(project_folder).joinpath(input_path)

        # create parent if not exists
        file_path.parent.mkdir(parents=True, exist_ok=True)

        file_path.touch(exist_ok=True)
        self.window.open_file(str(file_path))

    def is_visible(self, dirs: "list[str]"):
        return len(dirs) == 1
