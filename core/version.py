"""Application version, plus the deployed git commit when running from a checkout."""
import os

__version__ = "2.1"  # matches the git tag; bump both together

_REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def git_commit():
    """Short hash of the checked-out commit, read straight from .git (no git binary needed)."""
    git_dir = os.path.join(_REPO_DIR, ".git")
    try:
        with open(os.path.join(git_dir, "HEAD"), encoding="utf-8") as f:
            head = f.read().strip()
        if not head.startswith("ref: "):
            return head[:7]  # detached HEAD
        ref = head[5:]
        ref_path = os.path.join(git_dir, *ref.split("/"))
        if os.path.exists(ref_path):
            with open(ref_path, encoding="utf-8") as f:
                return f.read().strip()[:7]
        with open(os.path.join(git_dir, "packed-refs"), encoding="utf-8") as f:
            for line in f:
                parts = line.split()
                if len(parts) == 2 and parts[1] == ref:
                    return parts[0][:7]
    except OSError:
        pass
    return None


# Resolved once at import: the running code doesn't change until a restart
GIT_COMMIT = git_commit()
