#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2020 Bayerische Motoren Werke Aktiengesellschaft (BMW AG)
#
# SPDX-License-Identifier: GPL-2.0-only

import argparse
import csv
import os
import sys
import re

import pandas as pd
from tabulate import tabulate

################################################################################


def df_from_csv_file(name):
    df = pd.read_csv(name, na_values=['None'], keep_default_na=True)
    df[['Commit_datetime', 'Refcommit_datetime']] = df[
        ['Commit_datetime', 'Refcommit_datetime']
    ].apply(pd.to_datetime, utc=True)
    df.reset_index(drop=True, inplace=True)
    return df


def df_to_csv_file(df, name):
    df.to_csv(
        path_or_buf=name,
        quoting=csv.QUOTE_ALL,
        sep=",", index=False, encoding='utf-8')
    print("[+] Wrote: %s" % name)


def array_from_blacklist_file(name):
    pattern = re.compile(r'\b[0-9a-f]{10,40}\b')
    matches = None
    if name:
        with open(name) as f:
            text = f.read()
            matches = re.findall(pattern, text)
    return matches


def missing_fixes_based_on(
        left_csv=None, left_col='Commit_upstream_hexsha',
        right_csv=None, right_col='Refcommit_hexsha'):

    df_left = df_from_csv_file(left_csv)
    df_right = df_from_csv_file(right_csv)

    # Find unique non-null commits in left_csv.left_col
    df_left_sel = df_left.drop_duplicates(subset=left_col, keep='last')
    df_left_sel = df_left_sel[df_left_sel[left_col].notnull()]

    # Find unique non-null commits in right_csv.right_col
    df_right_sel = df_right.drop_duplicates(subset=right_col, keep='last')
    df_right_sel = df_right_sel[df_right_sel[right_col].notnull()]

    # For the rows where df_right_sel.Commit_upstream_hexsha value is missing,
    # use the value from column df_right_sel.Commit_hexsha.
    # This makes it possible to use non-stable branches in right_csv.
    colname = 'Commit_upstream_hexsha'
    df_right_sel.loc[
        df_right_sel[colname].isnull(), colname] = df_right_sel['Commit_hexsha']

    # Find common commits between left_cvs.left_col and right_csv.right_col
    # These are the commits fixed in right_csv, where the fixed commit
    # is included in left_csv
    df_common = df_left_sel.merge(
        df_right_sel,
        how='inner',
        left_on=[left_col],
        right_on=[right_col],
        suffixes=('_left', '_right'),
    )

    # Select commits from df_common where df_common.left_col_right
    # is *not* among df_left_sel.left_col
    # That is, where the potentially missing commit is not already included
    # in the left_csv.
    # After this merge and filter, we are left with commits  that are
    # potentially missing from left_csv
    df_missing = df_common.merge(
        df_left_sel,
        how='left',
        left_on=['%s_right' % left_col],
        right_on=[left_col],
        indicator=True,
    )
    df_missing = df_missing[df_missing['_merge'] == 'left_only']

    # Select only the relevant fields from df_missing
    df_missing = df_missing[
        [
            'Commit_upstream_hexsha_right',
            'Commit_hexsha_right',
            'Commit_summary_right',
            'Commit_upstream_hexsha_left',
            'Commit_hexsha_left',
        ]
    ]
    # Rename the selected columns
    df_missing.columns = [
        'Missing_commit_upstream',
        'Missing_commit_stable',
        'Missing_commit_summary',
        'Based_on_commit_upstream',
        'Based_on_commit_stable',
    ]

    return df_missing


def remove_blacklisted(df, blacklist_file, col='Missing_commit_upstream'):
    blacklist = array_from_blacklist_file(blacklist_file)
    if blacklist:
        df = df[~df[col].str.contains('|'.join(blacklist))]
    return df


def output(df, left_name, right_name, outname):

    print(
        "[+] %s is missing the below commits based "
        "on commits in %s:" %
        (os.path.basename(left_name), os.path.basename(right_name)))

    if df.empty:
        print("No missing fixes")
        return

    df = df.copy()

    # Add column 'Missing_commit', with values form 'Missing_commit_upstream'
    df['Missing_commit'] = df['Missing_commit_upstream']
    # For the rows where Missing_commit_upstream value is missing,
    # use the value from column Missing_commit_stable
    colname = 'Missing_commit'
    df.loc[df[colname].isnull(), colname] = df['Missing_commit_stable']
    # Add column 'Based_on_commit', with values form 'Based_on_commit_upstream'
    df['Based_on_commit'] = df['Based_on_commit_upstream']
    # Similarly, if Based_on_commit_upstream value is missing,
    # use the value from column Based_on_commit_stable
    colname = 'Based_on_commit'
    df.loc[df[colname].isnull(), colname] = df['Based_on_commit_stable']

    # Write the output to file
    df_to_csv_file(df, outname)

    # Select only the columns we want to print
    df = df[[
        'Missing_commit',
        'Missing_commit_summary',
        'Based_on_commit',
    ]]

    # Truncate the values
    df['Missing_commit'] = df['Missing_commit'].str.slice(0, 12)
    df['Missing_commit_summary'] = df['Missing_commit_summary'].str.slice(0, 64)
    df['Based_on_commit'] = df['Based_on_commit'].str.slice(0, 12)

    print("")
    print(tabulate(df, headers='keys', tablefmt='simple', showindex=False))
    print("")


def exit_unless_accessible(filename):
    if not os.path.isfile(filename):
        sys.stderr.write(
            "Error: file not found or no permissions: %s\n" % filename)
        sys.exit(1)


def getargs():
    desc = \
        "Script finds potentially missing commits from "\
        "the specified branch CSV1, based on commits "\
        "in another branch CSV2. Script determines possible missing "\
        "commits based on commit references. That is, if a commit [C] "\
        "is referenced in another commit [R] in branch CSV2 and, "\
        "based on upstream references, commit [C] is included "\
        "in branch CSV1 without the referencing commit [R], then [R] is "\
        "potentially missing from branch CSV1. "\
        "Note: the produced list of missing patches requires "\
        "manual effort to find out if the found missing patches "\
        "would actually apply to branch CSV1."

    epil = "Example: ./%s linux-stable-rc.csv linux-next.csv" % \
        os.path.basename(__file__)
    parser = argparse.ArgumentParser(description=desc, epilog=epil)

    help = \
        "CSV database for the branch which will be checked for "\
        "potential missing commits "\
        "(output from xrefdb.py)"
    parser.add_argument('CSV1', nargs=1, help=help)

    help = \
        "CSV database for the branch which will used as reference "\
        "to find potential missing commits from CSV1 "\
        "(output from xrefdb.py)"
    parser.add_argument('CSV2', nargs=1, help=help)

    help = "set the blacklist file name; blacklist file is a text file "\
           "that lists the CSV2 commit hexshas that are intentionally "\
           "not applied to CSV1 and should thus be left out from the "\
           "produced list of missing commits"

    parser.add_argument('--blacklist', nargs='?', help=help)

    help = "set the output file name, default is 'missing.csv'"
    parser.add_argument('--out', nargs='?', help=help, default='missing.csv')

    return parser.parse_args()

################################################################################


if __name__ == "__main__":
    if sys.version_info[0] < 3:
        sys.stderr.write("Error: script requires Python 3.x\n")
        sys.exit(1)

    args = getargs()
    left = args.CSV1[0]
    right = args.CSV2[0]
    out = args.out
    blacklist = args.blacklist

    exit_unless_accessible(left)
    exit_unless_accessible(right)
    if blacklist:
        exit_unless_accessible(blacklist)

    print("[+] Reading input csv files, this might take a few minutes")

    # Find missing fixes based on upstream references:
    # where left.Commit_upstream_hexsha matches right.Refcommit_hexsha.
    # These are cases where the "Fixes" or "Revert" points back to an upstream
    # commit.
    df_upstream = missing_fixes_based_on(
        left, "Commit_upstream_hexsha",
        right, "Refcommit_hexsha"
    )

    # Find missing fixes based on local references:
    # where left.Commit_hexsha matches right.Refcommit_hexsha.
    # These are cases where the "Fixes" or "Revert" points back to a local
    # commit, not an upstream commit.
    df_local = missing_fixes_based_on(
        left, "Commit_hexsha",
        right, "Refcommit_hexsha"
    )

    df = pd.concat([df_upstream, df_local])

    # Remove blacklisted entries
    df = remove_blacklisted(df, blacklist)

    # Output table and csv-file
    output(df, left, right, out)

################################################################################
