"""QT Tools"""

import subprocess

import sublime
import sublime_plugin


class QttoolsOpenDesignerCommand(sublime_plugin.TextCommand):
    def run(self, edit: sublime.Edit):
        file_path = self.view.file_name()
        subprocess.Popen(["designer", file_path])

    def is_visible(self):
        return self.view.match_selector(0, "text.qt.ui")
