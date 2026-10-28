"""Regression snapshot of every text output.

    tools/regress.py > snapshot.txt
    diff old.txt new.txt

Runs translate (on examples/*.txt), gloss, read, check and write (on
examples/*.sera) and prints their output in one stream, so a change to the
grammar, translator or reader shows up as a diff. The user lexicon is copied
into a throwaway XDG_DATA_HOME, so coined words are stable between runs and the
real one is never written."""
import glob
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
EX = os.path.join(ROOT, "examples")
VIDEO_GLOSS = "NPFV NEG.ever 1S comprehend-OBJ ABS-Aghma_Shwa CON-allure"


def run(env, *args, stdin=None):
    p = subprocess.run([sys.executable, "-m", "seraphim", *args], input=stdin, env=env,
                       capture_output=True, text=True, cwd=ROOT)
    return p.stdout + (f"[stderr]\n{p.stderr}" if p.stderr.strip() else "") + f"[exit {p.returncode}]\n"


def main():
    tmp = tempfile.mkdtemp(prefix="seraphim-regress-")
    try:
        user = os.path.join(os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share")),
                            "seraphim", "lexicon.tsv")
        os.makedirs(os.path.join(tmp, "seraphim"))
        if os.path.exists(user):
            shutil.copy(user, os.path.join(tmp, "seraphim", "lexicon.tsv"))
        env = dict(os.environ, XDG_DATA_HOME=tmp, PYTHONPATH=ROOT, NO_COLOR="1")
        cases = []
        for txt in sorted(glob.glob(os.path.join(EX, "*.txt"))):
            cases.append((f"translate {os.path.basename(txt)}",
                          ("translate", "--no-save"), open(txt, encoding="utf-8").read()))
        cases.append(("gloss video", ("gloss", "--no-save", VIDEO_GLOSS, "--tense", "farpast"), None))
        for sera in sorted(glob.glob(os.path.join(EX, "*.sera"))):
            for cmd in ("read", "check", "write"):
                cases.append((f"{cmd} {os.path.basename(sera)}", (cmd, sera), None))
        for name, args, stdin in cases:
            print(f"===== {name}")
            print(run(env, *args, stdin=stdin), end="")
    finally:
        shutil.rmtree(tmp)


if __name__ == "__main__":
    main()
