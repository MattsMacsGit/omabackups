"""One error type for everything the user can hit.

Every error says what happened, what to do about it, and carries details the
user can copy into a bug report or a message for help.
"""

import traceback


class OmaError(Exception):
    def __init__(self, what: str, todo: str = "", details: str = "", code: str = "error"):
        super().__init__(what)
        self.what = what
        self.todo = todo
        self.details = details
        self.code = code  # short machine name, e.g. "bad-settings"

    def as_dict(self) -> dict:
        return {"code": self.code, "what": self.what, "todo": self.todo, "details": self.details}

    def as_text(self) -> str:
        lines = [self.what]
        if self.todo:
            lines.append(self.todo)
        if self.details:
            lines += ["", "Details to copy:", self.details]
        return "\n".join(lines)


def unexpected(exc: BaseException) -> OmaError:
    """Wrap a bug (an error we didn't plan for) so it still reads properly."""
    return OmaError(
        "Something went wrong inside OmaBackups.",
        "Nothing was changed by this step. If it happens again, please report "
        "it with the details below.",
        "".join(traceback.format_exception(exc)).strip(),
        code="unexpected",
    )
