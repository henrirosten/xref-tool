#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2020 Bayerische Motoren Werke Aktiengesellschaft (BMW AG)
#
# SPDX-License-Identifier: GPL-2.0-only

import re
import git
import csv
import argparse
import os
import sys
import pandas as pd

################################################################################


class XrefDb:

    def __init__(self, gitdir, rev):
        self.gitdir = gitdir
        # Stats are generated based on the git commit entries in the
        # specified git repository in the given revision range
        self.rev = rev
        # Dictionary to store the csv data
        # Key: column header, Value: list of entries
        self.entries = {}
        # GitPython Repo object
        self.repo = git.Repo(self.gitdir)
        # Map a stable commit to an upstream commit
        # Key: stable commit sha, Value: upstream commit sha
        self.mapcommittoupstream = {}
        self._build_upstreamindex()

    def find_references(self):
        for commit in list(self.repo.iter_commits(self.rev, reverse=True)):
            self._find_references(commit)

    def to_csv(self, filename):
        df = pd.DataFrame(self.entries)
        # Sort columns alphabetically
        df = df.sort_index(axis=1)
        df.to_csv(path_or_buf=filename, quoting=csv.QUOTE_ALL,
                  sep=",", index=False, encoding='utf-8')

    def _get_long_commit_sha(self, sha):
        if not sha:
            return None
        if len(sha) >= 40:
            return sha
        try:
            return self.repo.git.rev_parse(sha)
        except git.GitCommandError:
            return None

    def _get_commit(self, commitsha):
        if not commitsha:
            return None
        try:
            return self.repo.commit(commitsha)
        except ValueError:
            return None

    def _find_references(self, commit):
        refset = set()

        # Find referenced commit shas ("Fixes:" and "Revert" tags)
        for line in commit.message.splitlines():
            refsha = self._match_referenced_sha(line)
            if refsha:
                refset.add(refsha)

        # If no referenced commits were found, we still want to output
        # ("stamp") the commit; therefore, add an "empty" reference
        if not refset:
            refset.add("")

        # Output all found pairs of [referenced_commit, commit]
        for refsha in refset:
            self._stamp_commit(refsha, commit)

    def _stamp_commit(self, refsha, commit):
        ref_commit = self._get_commit(refsha)
        if not ref_commit:
            ref_sha = ""
            ref_datetime = ""
        else:
            if ref_commit.hexsha == commit.hexsha:
                print("[+] Warning: ignored commit where referenced commit "
                      "and fix are the same (%s)" % (commit.hexsha))
                return
            ref_sha = ref_commit.hexsha
            ref_datetime = ref_commit.committed_datetime

        commit_upstream_hexsha = self.mapcommittoupstream.get(
            commit.hexsha, "")
        ref_upstream_hexsha = self.mapcommittoupstream.get(ref_sha, "")

        setcol = self.entries.setdefault
        setcol('Commit_hexsha', []).append(commit.hexsha)
        setcol('Commit_summary', []).append(commit.summary)
        setcol('Commit_datetime', []).append(commit.committed_datetime)
        setcol('Commit_upstream_hexsha', []).append(commit_upstream_hexsha)
        setcol('Refcommit_hexsha', []).append(ref_sha)
        setcol('Refcommit_datetime', []).append(ref_datetime)
        setcol('Refcommit_upstream_hexsha', []).append(ref_upstream_hexsha)

    def _match_referenced_sha(self, line):
        RE_REVERT_SHA = re.compile(
            r'.*[Rr]evert.{0,10}commit.*\s+(?P<sha>[0-9a-f]{5,40})\b')
        RE_FIXES_SHA = re.compile(
            r'.*[Ff]ixes.{0,10}\s+(?P<sha>[0-9a-f]{5,40})\b')
        refsha = ""
        match = ""
        if not match:
            # (1) Try matching lines like: "This reverts commit SHA_HERE"
            match = RE_REVERT_SHA.match(line)
        if not match:
            # (2) Try matching lines like: "Fixes: SHA_HERE"
            match = RE_FIXES_SHA.match(line)
        if match:
            refsha = match.group('sha')
            refsha = self._get_long_commit_sha(refsha)
        return refsha

    def _build_upstreamindex(self):
        RE_UPSTREAM_1 = re.compile(
            # Negative lookbehind:
            # Match (1) that is not preceded by (2), (3), (4), or (5)
            # We need this because below is a valid upstream reference:
            #     commit HEXSHA1 upstream.
            # Whereas, this is not a valid upstream reference:
            #     This reverts commit HEXSHA2 which is
            #     commit HEXSHA1 upstream.
            r'(?<!reverts commit [0-9a-f]{40} which is)'    # (2)
            r'(?<!reverts commit [0-9a-f]{40}, which is)'   # (3)
            r'(?<!reverts commit [0-9a-f]{40} which was)'   # (4)
            r'(?<!reverts commit [0-9a-f]{40}, which was)'  # (5)
            r'$'
            # (1)
            r'\s*\[?\s*[Cc]omm?[it]{2}\s*(?P<sha>[0-9a-f]{10,40})\s+[Uu]pst?ream\.?\s*\]?\s*$',
            re.MULTILINE)
        RE_UPSTREAM_2 = re.compile(
            r'(?<!reverts commit [0-9a-f]{40} which is)'    # (2)
            r'(?<!reverts commit [0-9a-f]{40}, which is)'   # (3)
            r'(?<!reverts commit [0-9a-f]{40} which was)'   # (4)
            r'(?<!reverts commit [0-9a-f]{40}, which was)'  # (5)
            r'$'
            # (1)
            r'^\s*\[?\s*[Uu]pst?ream\s+[Cc]omm?[it]{2}\s*(?P<sha>[0-9a-f]{40})',
            re.MULTILINE)
        for commit in list(self.repo.iter_commits(self.rev)):
            match = ""
            if not match:
                match = RE_UPSTREAM_1.search(commit.message)
            if not match:
                match = RE_UPSTREAM_2.search(commit.message)
            if match:
                upstreamsha = match.group('sha')
                upstreamsha = self._get_long_commit_sha(upstreamsha)
                if not upstreamsha:
                    # _get_long_commit_sha() returns None if
                    # upstreamsha is not in the git tree. We'll ignore
                    # such upstream references.
                    continue
                sha = commit.hexsha
                self.mapcommittoupstream[sha] = upstreamsha

################################################################################


def getargs():
    desc = \
        "Find commit cross-references from a kernel git repository "\
        "GIT_DIR analyzing commits specified by revision REV. "\
        "Cross-references include commits referenced in other commit's fixes "\
        "or revert tags, or upstream reference line. Output is a "\
        "csv file that lists all the revision range REV commits "\
        "in reverse chronological order. For each commit, the output "\
        "includes commit hexsha 'Commit_hexsha', and other columns "\
        "that specify the cross-references. For instance, column "\
        "'Commit_upstream_hexsha' specifies the upstream commit "\
        "(if any) corresponding the 'Commit_hexsha' in the upstream, "\
        "and 'Refcommit_hexsha' specifies the referenced commit based "\
        "on fixes or revert tags."

    epil = "Example: ./%s --git-dir ~/linux-stable/ v4.19^..v4.19.110" %\
        os.path.basename(__file__)
    parser = argparse.ArgumentParser(description=desc, epilog=epil)

    help = "revision specifier, see git-rev-parse for viable options. "
    parser.add_argument('REV', nargs=1, help=help)

    help = "file path to git repository, defaults to current working directory"
    parser.add_argument('--git-dir', nargs='?', help=help, default='./')

    help = "set the output file name, default is 'xrefdb.csv'"
    parser.add_argument('--out', nargs='?', help=help, default='xrefdb.csv')

    return parser.parse_args()

################################################################################


if __name__ == "__main__":
    if sys.version_info[0] < 3:
        sys.stderr.write("Error: script requires Python 3.x\n")
        sys.exit(1)

    args = getargs()
    rev = args.REV[0]
    repo = args.git_dir
    outfile = args.out

    repo = repo if repo.endswith(".git") else os.path.join(repo, ".git")
    if(not (os.path.isdir(repo))):
        sys.stderr.write("Error: not a git repository: %s\n" % repo)
        sys.exit(1)

    print("[+] Reading commit history, this might take a few minutes")
    stats = XrefDb(repo, rev)
    stats.find_references()
    stats.to_csv(outfile)
    print("[+] Wrote file: %s" % outfile)

################################################################################
