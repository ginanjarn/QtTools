"""QT Tools"""

import os
import subprocess
import threading

from dataclasses import dataclass, asdict
from abc import ABC, abstractmethod
from enum import Enum
from pathlib import Path
from typing import List, Dict

from string import Template as StringTemplate

import sublime
import sublime_plugin

UI_VIEW_SELECTOR = "text.qt.ui"


def get_project_folder(path: str) -> str:
    folders = sublime.active_window().folders()

    candidates = [folder for folder in folders if path.startswith(folder)]
    if candidates:
        return max(candidates)

    raise ValueError("unable find project folders")


if os.name == "nt":
    # if on Windows, hide process window
    STARTUPINFO = subprocess.STARTUPINFO()
    STARTUPINFO.dwFlags |= subprocess.SW_HIDE | subprocess.STARTF_USESHOWWINDOW
else:
    STARTUPINFO = None


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


class QttoolsGenerateCodeCommand(sublime_plugin.TextCommand):
    suffix_map = {
        "cpp": ".h",
        "python": ".py",
    }

    def run(self, edit: sublime.Edit):
        thread = threading.Thread(target=self._run, args=(edit,))
        thread.start()

    def _run(self, edit: sublime.Edit):
        file_name = self.view.file_name()
        language_options = list(self.suffix_map.keys())
        language = ChoiceInput(
            language_options, placeholder="Target Language"
        ).get_value()
        if not language:
            return

        file_path = Path(file_name)
        default = file_path.stem + self.suffix_map[language]
        output_name = TextInput("Output name", initial_text=default).get_value()
        if not output_name:
            return

        try:
            process = subprocess.run(
                ["uic", "-g", language, file_name],
                startupinfo=STARTUPINFO,
                capture_output=True,
            )

        except FileNotFoundError:
            message = "Unable find Qt 'uic'.\nSet 'uic' directory in PATH."
            sublime.error_message(message)

        def normalize_newline(text: bytes) -> bytes:
            return text.replace(b"\r\n", b"\n")

        if process.returncode != 0:
            print(normalize_newline(process.stderr).decode())
            return

        output_path = Path(file_path.parent, output_name)
        output_path = output_path.with_suffix(self.suffix_map[language])

        output_path.write_text(normalize_newline(process.stdout).decode())
        print(f"Generated path: {output_path!s}")

    def is_visible(self):
        return self.view.match_selector(0, UI_VIEW_SELECTOR)


CURRENT_FILE_DIRECTORY = Path(__file__).parent


@dataclass
class ClassData:
    class_name: str
    baseclass_name: str = ""
    # __post__init__ defined value
    source_name: str = ""
    header_name: str = ""
    include_guard: str = ""
    ui_name: str = ""

    def __post_init__(self):
        if not self.class_name.isidentifier():
            raise ValueError(f"Invalid class name {self.class_name!r}")

        if not self.baseclass_name.isidentifier():
            raise ValueError(f"Invalid base class name {self.baseclass_name!r}")

        self.source_name = f"{self.class_name}.cpp"
        self.header_name = f"{self.class_name}.h"
        self.include_guard = f"{self.class_name.upper()}_H"
        self.ui_name = f"{self.class_name}.ui"


@dataclass
class File:
    path: Path
    text: str


@dataclass
class Project:
    path: Path
    files: List[File]


def write_project_files(project: Project):
    """"""
    for file in project.files:
        path = Path(project.path, file.path).resolve()
        path.write_text(file.text)


class InputCommand(ABC):
    @abstractmethod
    def get_value(self) -> str:
        """get input value"""


def set_event_on_done(event: threading.Event):
    def wrapper(func):
        def inner(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            finally:
                event.set()

        return inner

    return wrapper


class TextInput(InputCommand):
    def __init__(self, caption: str, initial_text: str = "") -> None:
        self.caption = caption
        self.initial_text = initial_text

    def get_value(self) -> str:
        event = threading.Event()
        result = ""

        @set_event_on_done(event)
        def on_done(text: str):
            nonlocal result
            result = text

        @set_event_on_done(event)
        def on_cancel():
            pass

        sublime.active_window().show_input_panel(
            self.caption,
            self.initial_text,
            on_change=None,
            on_done=on_done,
            on_cancel=on_cancel,
        )
        event.wait()
        return result


class ChoiceInput(InputCommand):
    def __init__(
        self, choices: List[str], placeholder: str = "", selected_index: int = -1
    ) -> None:
        self.choices = choices
        self.placeholder = placeholder
        self.selected_index = selected_index

    def get_value(self) -> str:
        event = threading.Event()
        result = ""

        @set_event_on_done(event)
        def on_select(index: int = -1):
            nonlocal result

            if index > -1:
                result = self.choices[index]

        sublime.active_window().show_quick_panel(
            self.choices,
            on_select=on_select,
            placeholder=self.placeholder,
            selected_index=self.selected_index,
        )
        event.wait()
        return result


class TemplateLoader:
    """"""

    template_directory = Path(sublime.packages_path(), "QtTools/template")

    def __init__(self, template: Path) -> None:
        self.template_path = Path(self.template_directory, template).resolve()

    def get_text(self, data: ClassData):
        """get text"""
        template = self.template_path.read_text()
        return StringTemplate(template).substitute(asdict(data))


class ProjectGenerator(ABC):
    def __init__(self, project_path: Path) -> None:
        self.project_path = Path(project_path)
        self.class_data: ClassData = None

    @abstractmethod
    def prepare(self):
        """"""

    @abstractmethod
    def generate(self) -> Project:
        """"""

    def get_text(self, template: Path) -> str:
        """get text from template"""
        return TemplateLoader(template).get_text(self.class_data)


class PlainClass(ProjectGenerator):
    def prepare(self):
        if class_name := TextInput("class name").get_value():
            self.class_data = ClassData(class_name)

    def generate(self) -> Project:
        files = []
        if self.class_data:
            files = [
                File(
                    self.class_data.header_name,
                    self.get_text("headers/plain.txt"),
                ),
                File(
                    self.class_data.source_name,
                    self.get_text("sources/plain.txt"),
                ),
            ]

        return Project(self.project_path, files)


class HeaderClass(ProjectGenerator):
    def prepare(self):
        if class_name := TextInput("class name").get_value():
            self.class_data = ClassData(class_name)

    def generate(self) -> Project:
        files = []
        if self.class_data:
            files = [
                File(
                    self.class_data.header_name,
                    self.get_text("headers/header.txt"),
                ),
            ]

        return Project(self.project_path, files)


class QObjectClass(ProjectGenerator):
    def prepare(self):
        qobject_classes = self._qobject_classes()
        selected_index = qobject_classes.index("QObject")

        baseclass_name = ChoiceInput(
            qobject_classes,
            placeholder="QObject Parent",
            selected_index=selected_index,
        ).get_value()
        if not baseclass_name:
            return

        default_name = baseclass_name[:1]
        class_name = TextInput("class name", initial_text=default_name).get_value()
        if not class_name:
            return

        self.class_data = ClassData(class_name, baseclass_name)

    def generate(self) -> Project:
        files = []
        if self.class_data:
            files = [
                File(
                    self.class_data.header_name,
                    self.get_text("headers/qobject.txt"),
                ),
                File(
                    self.class_data.source_name,
                    self.get_text("sources/qobject.txt"),
                ),
            ]

        return Project(self.project_path, files)

    qobject_data_path = Path(sublime.packages_path(), "QtTools/resource/qobjects.txt")

    def _qobject_classes(self):
        return self.qobject_data_path.read_text().splitlines()


class GuiClass(ProjectGenerator):
    def prepare(self):
        qobject_classes = ["QMainWindow", "QDialog", "QWidget"]
        selected_index = qobject_classes.index("QMainWindow")

        baseclass_name = ChoiceInput(
            qobject_classes,
            placeholder="Parent",
            selected_index=selected_index,
        ).get_value()

        if not baseclass_name:
            return

        default_name = baseclass_name[1:]
        class_name = TextInput("class name", initial_text=default_name).get_value()
        if not class_name:
            return

        self.class_data = ClassData(class_name, baseclass_name)

    def generate(self) -> Project:
        files = []
        if self.class_data:
            files = [
                File(
                    self.class_data.header_name,
                    self.get_text("headers/gui.txt"),
                ),
                File(
                    self.class_data.source_name,
                    self.get_text("sources/gui.txt"),
                ),
                File(
                    self.class_data.ui_name,
                    self.get_text(f"ui/{self.class_data.baseclass_name}.txt"),
                ),
            ]

        return Project(self.project_path, files)


class GuiFile(ProjectGenerator):
    def prepare(self):
        qobject_classes = ["QMainWindow", "QDialog", "QWidget"]
        selected_index = qobject_classes.index("QMainWindow")

        baseclass_name = ChoiceInput(
            qobject_classes,
            placeholder="Parent",
            selected_index=selected_index,
        ).get_value()

        if not baseclass_name:
            return

        default_name = baseclass_name[1:]
        class_name = TextInput("class name", initial_text=default_name).get_value()
        if not class_name:
            return

        self.class_data = ClassData(class_name, baseclass_name)

    def generate(self) -> Project:
        files = []
        if self.class_data:
            files = [
                File(
                    self.class_data.ui_name,
                    self.get_text(f"ui/{self.class_data.baseclass_name}.txt"),
                ),
            ]

        return Project(self.project_path, files)


class EmptyFile(ProjectGenerator):
    def prepare(self):

        self.file_name = TextInput(
            "File name",
        ).get_value()
        if not self.file_name:
            return

    def generate(self) -> Project:
        files = []
        if self.file_name:
            files = [File(self.file_name, "")]

        return Project(self.project_path, files)


class ClassKind(Enum):
    Plain = "plain"
    QObject = "qobject"
    Header = "header"
    Gui = "gui"


class FileKind(Enum):
    Empty = "empty"
    UiDesign = "ui_design"


_GENERATOR_MAP: Dict[ClassKind, ProjectGenerator] = {
    ClassKind.Plain: PlainClass,
    ClassKind.Header: HeaderClass,
    ClassKind.QObject: QObjectClass,
    ClassKind.Gui: GuiClass,
    FileKind.Empty: EmptyFile,
    FileKind.UiDesign: GuiFile,
}


class QttoolsCreateClassCommand(sublime_plugin.WindowCommand):
    """"""

    def run(self, kind: str, dirs: List[str]):
        thread = threading.Thread(target=self.run_task, args=(kind, dirs))
        thread.start()

    def run_task(self, kind: str, dirs: List[str]):
        generator = _GENERATOR_MAP[ClassKind(kind)]

        project_generator: ProjectGenerator = generator(dirs[0])
        project_generator.prepare()
        project = project_generator.generate()
        write_project_files(project)

    def is_visible(self, kind: str, dirs: List[str] = None):
        return bool(dirs) and len(dirs) == 1


class QttoolsCreateFileCommand(sublime_plugin.WindowCommand):
    """"""

    def run(self, kind: str, dirs: List[str]):
        thread = threading.Thread(target=self.run_task, args=(kind, dirs))
        thread.start()

    def run_task(self, kind: str, dirs: List[str]):
        generator = _GENERATOR_MAP[FileKind(kind)]

        project_generator: ProjectGenerator = generator(dirs[0])
        project_generator.prepare()
        project = project_generator.generate()
        write_project_files(project)

    def is_visible(self, kind: str, dirs: List[str] = None):
        return bool(dirs) and len(dirs) == 1
