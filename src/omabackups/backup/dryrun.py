"""`omabackups backup --dry-run`'s answer (audit 2.8): per part, what a
backup now would send and delete (backup/run.py runs the check)."""

from omabackups.backup import check, full


def summary(job) -> list[dict]:
    """Per part: what a backup now would send and delete (audit 2.8)."""
    out = []
    for part, _skip, new, plan in job.work:
        row = {"part": part.name, "files": None, "bytes": None, "deletes": 0, "moves": 0}
        if new is None:
            row["bytes"] = job.folder_sizes.get(part.name)
        elif isinstance(plan, full.FullList):
            row.update(files=len(plan.items), bytes=sum(size for _, size in plan.items))
            row["deletes"] = sum(op[0] == "delete" for op in plan.ops)
        elif plan is not None:
            row.update(files=len(plan.files), bytes=check.size_of(plan, str(new)))
            row["deletes"] = sum(op[0] == "delete" for op in plan.ops)
            row["moves"] = sum(op[0] == "rename" for op in plan.ops)
        out.append(row)
    return out
