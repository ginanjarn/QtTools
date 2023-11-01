"""QT Tools"""

import subprocess
import threading

from dataclasses import dataclass, asdict
from abc import ABC, abstractmethod
from enum import Enum
from pathlib import Path

from string import Template

import sublime
import sublime_plugin


class QttoolsOpenDesignerCommand(sublime_plugin.TextCommand):
    def run(self, edit: sublime.Edit):
        file_path = self.view.file_name()
        subprocess.Popen(["designer", file_path])

    def is_visible(self):
        return self.view.match_selector(0, "text.qt.ui")


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
    choices: list, placeholder: str = "", *, selected_index: int = -1, **kwargs
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

        self.source = self.class_name.lower() + ".cpp"
        self.header = self.class_name.lower() + ".h"
        self.include_guard = self.class_name.upper() + "_H"


def write_snippet(file_path: Path, text: str, config: Config, /):
    template = Template(text)
    new_text = template.substitute(asdict(config))
    file_path.write_text(new_text)


def get_template(file_name: str) -> str:
    path = CURRENT_FILE_DIRECTORY.joinpath("template", file_name)
    return path.read_text()


def check_assigned(obj: object, name: str, /):
    if not obj:
        raise ValueError(f"{name} not assigned")


class AbstractGenerator(ABC):
    """Abstract snippet generator"""

    @abstractmethod
    def configure(self):
        """configure parameters"""

    @abstractmethod
    def generate(self):
        """generate snippet"""


class PlainClass(AbstractGenerator):
    source_template = "class_plain_source.txt"
    header_template = "class_plain_header.txt"

    def __init__(self, base_path: Path):
        self.base_path = Path(base_path)
        self.config: Config = None

    def configure(self):
        class_name = text_input("Class name")
        self.config = Config(class_name)

        check_assigned(class_name, "class_name")

    def generate(self):
        source_path = self.base_path.joinpath(self.config.source)
        write_snippet(source_path, get_template(self.source_template), self.config)

        header_path = self.base_path.joinpath(self.config.header)
        write_snippet(header_path, get_template(self.header_template), self.config)


class InterfaceClass(AbstractGenerator):
    header_template = "class_interface_header.txt"

    def __init__(self, base_path: Path):
        self.base_path = Path(base_path)
        self.config: Config = None

    def configure(self):
        class_name = text_input("Class name")
        self.config = Config(class_name)

        check_assigned(class_name, "class_name")

    def generate(self):
        header_path = self.base_path.joinpath(self.config.header)
        write_snippet(header_path, get_template(self.header_template), self.config)


class QObjectClass(AbstractGenerator):
    source_template = "class_qobject_source.txt"
    header_template = "class_qobject_header.txt"

    def __init__(self, base_path: Path):
        self.base_path = Path(base_path)
        self.config: Config = None

    def configure(self):
        classes = QOBJECT_CLASSES
        baseclass_name = choice_input(classes, "Base Class", selected_index=0)
        class_name = text_input("Class name", initial_text=baseclass_name.lstrip("Q"))

        self.config = Config(class_name, baseclass_name)

        check_assigned(class_name, "class_name")
        check_assigned(baseclass_name, "baseclass_name")

    def generate(self):
        source_path = self.base_path.joinpath(self.config.source)
        write_snippet(source_path, get_template(self.source_template), self.config)

        header_path = self.base_path.joinpath(self.config.header)
        write_snippet(header_path, get_template(self.header_template), self.config)


class UiClass(AbstractGenerator):
    source_template = "class_ui_source.txt"
    header_template = "class_ui_header.txt"
    ui_template = "form_{baseclass}.txt"

    def __init__(self, base_path: Path):
        self.base_path = Path(base_path)
        self.config: Config = None

        self.create_class = False

    def configure(self):
        classes = ["QWidget", "QDialog", "QMainWindow"]
        baseclass_name = choice_input(classes, "Base Class", selected_index=0)
        self.create_class = yesno_input("Create Implementation Class")
        class_name = text_input("Class name", initial_text=baseclass_name.lstrip("Q"))

        self.config = Config(class_name, baseclass_name)

        check_assigned(class_name, "class_name")
        check_assigned(baseclass_name, "baseclass_name")

    def generate(self):
        ui_path = self.base_path.joinpath(self.config.source)
        ui_template = self.ui_template.format(
            baseclass=self.config.baseclass_name.lower()
        )
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


class QttoolsCreateClassCommand(sublime_plugin.WindowCommand):
    """"""

    def run(self, kind: str, paths: list):
        try:
            kind = ClassKind[kind]
        except KeyError:
            print("Error! Valid 'kind' argument:", [c.name for c in ClassKind])
            return

        if not paths:
            print("Error! Argument 'paths' must assiged.")
            return

        threading.Thread(
            target=self.run_task, kwargs={"kind": kind, "paths": paths}
        ).start()

    def run_task(self, kind: ClassKind, paths: list):
        if not paths:
            return

        base_path = Path(paths[0])
        if base_path.is_file():
            base_path = base_path.parent

        generator: AbstractGenerator = kind.value(base_path)
        generator.configure()
        generator.generate()
