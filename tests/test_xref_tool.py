#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2020 Bayerische Motoren Werke Aktiengesellschaft (BMW AG)
#
# SPDX-License-Identifier: GPL-2.0-only

import subprocess
import os
import pytest
import re
import shutil
from pathlib import Path
import sys


TESTS_DIR = Path(os.path.dirname(os.path.realpath(__file__)))
TEST_DATA_DIR = TESTS_DIR / "xref_tool_test_data"
TEST_DATA_TAR = TESTS_DIR / "xref_tool_test_data.tar.bz2"
XREFDB = TESTS_DIR / ".." / "xrefdb.py"
XREFMISSING = TESTS_DIR / ".." / "xrefmissing.py"
FINDMISSING = TESTS_DIR / ".." / "find-missing-commits.py"


@pytest.fixture()
def set_up_test_data():
    print("setup")
    shutil.rmtree(TEST_DATA_DIR, ignore_errors=True)
    assert subprocess.call(
        ["tar", "-xjf", TEST_DATA_TAR, "--directory", TESTS_DIR]) == 0
    yield "resource"
    print("clean up")
    shutil.rmtree(TEST_DATA_DIR)


def test_help():
    """
    Test help
    """
    cmd = [XREFDB, "-h"]
    assert subprocess.run(cmd).returncode == 0
    cmd = [XREFMISSING, "-h"]
    assert subprocess.run(cmd).returncode == 0


def test_xrefdb_basic(set_up_test_data):
    """
    Test that xrefdb.py runs and generates the expected output
    """
    gitdir = TEST_DATA_DIR / "v4.19.10"
    outfile = TEST_DATA_DIR / "xrefdb_out.csv"
    cmd = [XREFDB,
           "--git-dir", gitdir,
           "--out", outfile,
           "v4.19^..v4.19.1"]
    print(cmd)
    assert subprocess.run(cmd).returncode == 0
    assert Path(outfile).exists()

    # There should be exactly 26 commits in the range v4.19^..v4.19.1
    lines = sum(1 for line in open(outfile))
    assert(lines - 1 == 26)


def test_xrefdb_none(set_up_test_data):
    """
    Test that xrefdb.py runs and generates the expected output with empty rev
    """
    gitdir = TEST_DATA_DIR / "v4.19.10"
    outfile = TEST_DATA_DIR / "xrefdb_out.csv"
    cmd = [XREFDB,
           "--git-dir", gitdir,
           "--out", outfile,
           "v4.19..v4.19"]
    print(cmd)
    assert subprocess.run(cmd).returncode == 0
    assert Path(outfile).exists()

    # There should be no commits in the range v4.19..v4.19
    lines = sum(1 for line in open(outfile))
    assert(lines - 1 == 0)


def test_xrefmissing_basic(set_up_test_data):
    """
    Test that xrefmissing.py runs and generates the expected output when
    there are some missing commits, with and without the blacklist
    """
    gitdir = TEST_DATA_DIR / "v4.19.10"

    # Generate xrefdb files that will be used in this test
    left = TEST_DATA_DIR / "left.csv"
    cmd = [XREFDB,
           "--git-dir", gitdir,
           "--out", left,
           "v4.19^..v4.19.7"]
    print(cmd)
    assert subprocess.run(cmd).returncode == 0
    assert Path(left).exists()

    right = TEST_DATA_DIR / "right.csv"
    cmd = [XREFDB,
           "--git-dir", gitdir,
           "--out", right,
           "v4.19^..v4.19.10"]
    print(cmd)
    assert subprocess.run(cmd).returncode == 0
    assert Path(right).exists()

    outfile = TEST_DATA_DIR / "missing.csv"
    cmd = [XREFMISSING,
           left,
           right,
           "--out", outfile]
    assert subprocess.run(cmd).returncode == 0
    assert Path(outfile).exists()
    # There should be exactly 3 missing commits in the test range
    lines = sum(1 for line in open(outfile))
    assert(lines - 1 == 3)

    # Now run xrefmissing again, this time blacklisting one of the
    # missing commits
    outfile = TEST_DATA_DIR / "missing.csv"
    blacklist = TEST_DATA_DIR / "blacklist_v4.19.txt"
    cmd = [XREFMISSING,
           left,
           right,
           "--out", outfile,
           "--blacklist", blacklist]
    assert subprocess.run(cmd).returncode == 0
    assert Path(outfile).exists()
    # There should be exactly 2 missing commits after blacklisting
    # one of the original 3 missing commits
    lines = sum(1 for line in open(outfile))
    assert(lines - 1 == 2)


def test_xrefmissing_none(set_up_test_data):
    """
    Test that xrefmissing.py runs and generates the expected output when
    there are no missing commits
    """
    gitdir = TEST_DATA_DIR / "v4.19.10"

    # Generate xrefdb file that will be used in this test
    outfile = TEST_DATA_DIR / "xrefdb_out.csv"
    cmd = [XREFDB,
           "--git-dir", gitdir,
           "--out", outfile,
           "v4.19^..v4.19.1"]
    print(cmd)
    assert subprocess.run(cmd).returncode == 0
    assert Path(outfile).exists()

    # Comparing the xrefdb to itself should yield no results
    infile = outfile
    outfile = TEST_DATA_DIR / "missing.csv"
    cmd = [XREFMISSING,
           infile,
           infile,
           "--out", outfile]
    assert subprocess.run(cmd).returncode == 0

    # There should be no output file
    assert not Path(outfile).is_file()


def test_find_missing_commits_basic(set_up_test_data):
    """
    Test that find-missing-commits.py runs and generates the expected output
    with a blacklist file
    """

    # We need to edit the CHECKLIST for this test instance
    findmissing_temp = TEST_DATA_DIR / "find-missing-commits.py"
    cmd = ["cp", FINDMISSING, findmissing_temp]
    assert subprocess.run(cmd).returncode == 0
    checklist = '''
CHECKLIST = \\
    [
        {
            'stable_rev': 'v4.19^..v4.19.7',
            'stable_out': 'v4.19.7.csv',
            'other_rev': 'v4.19^..v4.19.10',
            'other_out': 'v4.19.10.csv',
            'missing_out': 'missingfixes.csv',
            'blacklist': '%s',
        },
    ]
    '''
    blacklist = TEST_DATA_DIR / "blacklist_v4.19.txt"
    checklist = checklist % blacklist
    text = None
    with open(findmissing_temp, 'r') as f:
        text = f.read()
        # replace CHECKLIST
        text = re.sub(
            r'(.*)CHECKLIST[^\]]+?\](.*)',
            r'\1' + checklist + r'\2',
            text,
            count=1,
            flags=re.MULTILINE)
        # replace XREFDB
        text = re.sub(
            r'XREFDB = .*',
            "XREFDB = \"%s\"" % XREFDB,
            text,
            count=1)
        # replace XREFMISSING
        text = re.sub(
            r'XREFMISSING = .*',
            "XREFMISSING = \"%s\"" % XREFMISSING,
            text,
            count=1)
    assert text is not None
    with open(findmissing_temp, 'w') as f:
        f.write(text)

    # Run it
    gitdir = TEST_DATA_DIR / "v4.19.10"
    outfile = TEST_DATA_DIR / "xrefdb_out.csv"
    outdir = TEST_DATA_DIR / "missing"
    cmd = [findmissing_temp,
           "--stable", gitdir,
           "--other", gitdir,
           "--dst", outdir]
    assert subprocess.run(cmd).returncode == 0
    outfile = outdir / "missingfixes.csv"
    # There should be exactly 2 missing commits after blacklisting
    # one of the original 3 missing commits
    lines = sum(1 for line in open(outfile))
    assert(lines - 1 == 2)


if __name__ == '__main__':
    pytest.main([__file__])
