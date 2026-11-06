"""What the omabackups command tells the panel and the terminal screens.

With --json, every line on stdout is one JSON object (an "event"):
  {"event": "step",     "step": "...", "message": "..."}
  {"event": "progress", "percent": 42.0, "seconds_left": 30, "message": "..."}
  {"event": "message",  "message": "..."}
  {"event": "error",    "code": "...", "what": "...", "todo": "...", "details": "..."}
  {"event": "result",   ...the command's answer...}
Each carries "contract" (the version of this format, BUILD 5.10).
Without --json, people get plain sentences instead.
"""

import json
import sys

from omabackups import CONTRACT


class Events:
    def __init__(self, as_json: bool = False, out=None, err=None):
        self.as_json = as_json
        self.out = out or sys.stdout
        self.err = err or sys.stderr

    def _emit(self, event: str, fields: dict) -> None:
        line = json.dumps({"event": event, "contract": CONTRACT, **fields}, sort_keys=True)
        self.out.write(line + "\n")
        self.out.flush()

    def step(self, step: str, message: str) -> None:
        if self.as_json:
            self._emit("step", {"step": step, "message": message})
        else:
            self._say(message)

    def progress(self, percent: float, message: str = "", seconds_left: int | None = None) -> None:
        percent = max(0.0, min(100.0, float(percent)))
        if self.as_json:
            self._emit("progress", {"percent": round(percent, 1),
                                    "seconds_left": seconds_left, "message": message})
        # Plain mode: the terminal screens draw their own bars; nothing here.

    def message(self, message: str) -> None:
        if self.as_json:
            self._emit("message", {"message": message})
        else:
            self._say(message)

    def error(self, error) -> None:
        """Show an OmaError. In JSON mode it goes to stdout as an event too."""
        if self.as_json:
            self._emit("error", error.as_dict())
        self.err.write(error.as_text() + "\n")
        self.err.flush()

    def result(self, data: dict, text: str) -> None:
        """The command's answer: JSON for programs, `text` for people."""
        if self.as_json:
            self._emit("result", data)
        else:
            self._say(text)

    def _say(self, text: str) -> None:
        self.out.write(text.rstrip("\n") + "\n")
        self.out.flush()
