#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2020 Bayerische Motoren Werke Aktiengesellschaft (BMW AG)
#
# SPDX-License-Identifier: GPL-2.0-only

import shutil
import argparse
import os
import sys
import re
from pathlib import Path
import subprocess

################################################################################

# Which stable revisions are checked and against which other revisions?
CHECKLIST = \
    [
        {
            # Missing from linux-stable v5.4 based on fixes in
            # linux-next v5.4^..origin/pending-fixes
            'stable_rev': 'v5.4^..origin/linux-5.4.y',
            'stable_out': 'stable-v5.4.csv',
            'other_rev': 'v5.4^..origin/pending-fixes',
            'other_out': 'linux-next_v5.4_pending-fixes.csv',
            'missing_out': 'missing-from_v5.4_based-on_linux-next-v5.4-pending-fixes.csv',
            'blacklist': '',
        },
        {
            # Missing from linux-stable v4.19 based on fixes in
            # linux-next v5.4^..origin/pending-fixes
            'stable_rev': 'v4.19^..origin/linux-4.19.y',
            'stable_out': 'stable-v4.19.csv',
            'other_rev': 'v5.4^..origin/pending-fixes',
            'other_out': 'linux-next_v5.4_pending-fixes.csv',
            'missing_out': 'missing-from_v4.19_based-on_linux-next-v5.4-pending-fixes.csv',
            'blacklist': '',
        },
    ]

SCRIPT_DIR = Path(os.path.abspath((os.path.dirname(__file__))))
WORKING_DIR = Path(os.getcwd())
XREFDB = "./" / SCRIPT_DIR / "xrefdb.py"
XREFMISSING = "./" / SCRIPT_DIR / "xrefmissing.py"

################################################################################


def exec_cmd(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE):
    pipe = subprocess.Popen(
        cmd, shell=True, stdout=stdout, stderr=stderr, encoding='utf-8')
    stdout, stderr = pipe.communicate()
    if pipe.returncode != 0:
        raise ValueError(stderr)
    return stdout


def findmissing(dstfolder, lstable, lother):
    dstdir = WORKING_DIR / dstfolder
    dstdir.mkdir(parents=True, exist_ok=True)

    for item in CHECKLIST:
        stable_out = dstdir / item['stable_out']
        other_out = dstdir / item['other_out']
        missing_out = dstdir / item['missing_out']
        blacklist = item['blacklist']
        blacklist_opt = ("--blacklist %s" % blacklist) if blacklist else ""

        if not os.path.isfile(stable_out):
            cmd = "%s --git-dir %s --out %s %s" % (
                XREFDB, lstable, stable_out, item['stable_rev'])
            exec_cmd(cmd)

        if not os.path.isfile(other_out):
            cmd = "%s --git-dir %s --out %s %s" % (
                XREFDB, lother, other_out, item['other_rev'])
            exec_cmd(cmd)

        cmd = "%s %s %s --out %s %s" % (
            XREFMISSING, stable_out, other_out, missing_out, blacklist_opt)
        ret = exec_cmd(cmd)
        match = re.search(r'.*(\[\+\].+)', ret, re.MULTILINE | re.DOTALL)
        if match:
            print(match.group(1).strip())
        print("")


def prompt_if_exists(dstfolder):
    if dstfolder.exists():
        prompt = \
            "This will remove earlier content from \"%s\". "\
            "Are you sure? (y/N): " % dstfolder
        if input(prompt) != 'y':
            print("Cancelled")
            sys.exit(0)


def rm_r(path):
    if os.path.isdir(path) and not os.path.islink(path):
        shutil.rmtree(path)
    elif os.path.exists(path):
        os.remove(path)


def exit_unless_exists(filename):
    if not os.path.isfile(filename):
        sys.stderr.write(
            "Error: script requires \"%s\", which was not found on "
            "the current dir.\n" % filename)
        sys.exit(1)


def verify_rev(gitdir, rev):
    try:
        cmd = "git --git-dir %s rev-parse %s" % (gitdir, rev)
        exec_cmd(cmd)
    except ValueError:
        sys.stderr.write(
            "Error: git revision \"%s\" is unknown "
            "in repository \"%s\"\n" % (rev, gitdir))
        sys.exit(1)


def verify_checklist(stabledir, otherdir, checklist):
    for item in checklist:
        blacklist = item['blacklist']
        if blacklist and not os.path.isfile(blacklist):
            sys.stderr.write(
                "Error: blacklist file \"%s\" not found or no "
                "permissions.\n" % blacklist)
            sys.exit(1)

        verify_rev(stabledir, item['stable_rev'])
        verify_rev(otherdir, item['other_rev'])


def getargs():
    desc = \
        "This script is a simple front-end to xrefdb.py and "\
        "xrefmissing.py to make it easier to update the "\
        "list of potentially missing commits from stable releases "\
        "based on pre-defined revision ranges. "\
        "Given a path to linux-stable git repository (--stable) and "\
        "another linux repository (--other), this script calls "\
        "xrefdb.py and xrefmissing.py to "\
        "find commits potentially missing from stable tree based on "\
        "commits in the other kernel tree. " \
        "You may want to modify the checked kernel branches and revisions, "\
        "by editing the CHECKLIST array defined at the top of "\
        "this script. "\
        "Note: the produced list of missing patches requires "\
        "manual effort to determine if the found missing patches "\
        "would actually apply to stable."

    epil = "Example: ./%s --stable ~/stable --other ~/linux-next" % \
        os.path.basename(__file__)
    parser = argparse.ArgumentParser(description=desc, epilog=epil)

    help = "file path to linux-stable git repository"
    parser.add_argument('--stable', required=True, help=help)

    help = "file path to another kernel git repository"
    parser.add_argument('--other', required=True, help=help)

    help = "set the destination folder, defaults to ./missing_fixes"
    parser.add_argument(
        '-d', '--dst', nargs='?', help=help, default='./missing_fixes')

    return parser.parse_args()

################################################################################


if __name__ == "__main__":
    if sys.version_info[0] < 3:
        sys.stderr.write("Error: script requires Python 3.x\n")
        sys.exit(1)

    args = getargs()
    dstdir = Path(args.dst)
    lstable = args.stable
    lother = args.other

    lstable = lstable if lstable.endswith(".git") else os.path.join(lstable, ".git")
    if(not (os.path.isdir(lstable))):
        sys.stderr.write("Error: not a git repository: %s\n" % lstable)
        sys.exit(1)

    lother = lother if lother.endswith(".git") else os.path.join(lother, ".git")
    if(not (os.path.isdir(lother))):
        sys.stderr.write("Error: not a git repository: %s\n" % lother)
        sys.exit(1)

    exit_unless_exists(XREFDB)
    exit_unless_exists(XREFMISSING)
    verify_checklist(lstable, lother, CHECKLIST)

    prompt_if_exists(dstdir)
    rm_r(dstdir)
    print("[+] Reading commit history, this might take a few minutes")
    findmissing(dstdir, lstable, lother)

    print("[+] Done, for more details, see: %s" % dstdir.absolute())

################################################################################
