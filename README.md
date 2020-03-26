<!--
SPDX-FileCopyrightText: 2020 Bayerische Motoren Werke Aktiengesellschaft (BMW AG)

SPDX-License-Identifier: GPL-2.0-only
-->

# Kernel Cross-Reference Commits

This repository is a collection of scripts for gathering data on kernel commits referencing each other via Fixes, Revert, and Upstream tags.

## Table of contents
* [Getting Started](#getting-started)
* [Building Cross-Reference Database](#building-cross-reference-database)
* [Finding Missing Commits Based on Cross-References](#finding-missing-commits-based-on-cross-references)
* [Finding Missing Commits Using a Helper Script](#finding-missing-commits-using-a-helper-script)

## Getting Started
Scripts require python3:
```
$ sudo apt install python3 python3-pip
```

In addition, the scripts rely on a number of python packages specified in requirements.txt. You can install the required packages with:
```
$ pip3 install -r requirements.txt
```

## Building Cross-Reference Database
[xrefdb.py](xrefdb.py) builds cross-reference database based on "Fixes", "Revert", and "Upstream" tags in the kernel git changelogs.

As an example, the below command finds the cross-references from the repository in local path ~/linux-stable from commits between tags v4.19 and v4.19.100, producing the output to file xrefdb_v4.19-v4.19.100.csv:
```
$ ./xrefdb.py --git-dir ~/linux-stable --out xrefdb_v4.19-v4.19.100.csv v4.19^..v4.19.100
```
Output is a CSV database that lists all commits in the specified revision range in chronological order by commit time. For each commit, the CSV database includes fields such as: Commit_hexsha, Commit_summary, and Commit_upstream_hexsha that specify the commit hexsha, one line summary, and upstream commit hexsha respectively. Fields such as Refcommit_hexsha and Refcommit_upstream_hexsha specify the commit referenced by the Commit_hexsha on the same row. "References" include fixes and revert tags, extracted from the Commit_hexsha commit message. That is, if Refcommit_hexsha is not empty, it specifies the commit that was fixed or reverted by Commit_hexsha. Similarly, if Commit_upstream_hexsha is not empty, it specifies the upstream commit corresponding the Commit_hexsha in the upstream.


## Finding Missing Commits Based on Cross-References
[xrefmissing.py](xrefmissing.py) finds potentially missing commits given two cross-reference database files as input. That is, xrefmissing.py determines the missing commits from the specified cross-reference database CSV1 based on commits in another database CSV2. Specifically, if a commit [C] is referenced in another commit [R] in database CSV2 and, based on upstream references, commit [C] is included in CSV1 without the referencing commit [R], then [R] is potentially missing from CSV1.

As an example, given the cross-reference database for linux-stable v4.19:
```
$ ./xrefdb.py --git-dir ~/linux-stable --out v4.19.csv v4.19^..origin/linux-4.19.y
```

as well as for linux-stable v5.4:
```
$ ./xrefdb.py --git-dir ~/linux-stable --out v5.4.csv v5.4^..origin/linux-5.4.y
```

the below command finds the potentially missing fixes from linux-stable v4.19 based on commits in v5.4:
```
$ ./xrefmissing.py v4.19.csv v5.4.csv
```
```
Missing_commit    Missing_commit_summary                                            Based_on_commit
----------------  ----------------------------------------------------------------  -----------------
ca9033ba69c7      IB/hfi1: Don't cancel unused work item                            4d43d395fed1
f667216c5c7c      mmc: sdhci-of-esdhc: re-implement erratum A-009204 workaround     5dd195522562
dc8d37ed304e      cpu/SMT: Fix x86 link error without CONFIG_SYSFS                  ec527c318036
e19ecbf105b2      ASoC: sgtl5000: Fix VDDA and VDDIO comparison                     b6319b061ba2
23f61b9fc5cc      EDAC/ghes: Fix locking and memory barrier issues                  1e72e673b9d1
396d2e878f92      kvm: x86: Host feature SSBD doesn't imply guest feature SPEC_CTR  0c54914d0c52
e9f930ac88a8      iomap: fix return value of iomap_dio_bio_actor on 32bit systems   4721a6010990
24885d1d79e2      KVM: x86: Remove a spurious export of a static function           cbbaa2727aa3
eb014de4fd41      netfilter: nf_tables: autoload modules from the abort path        ec7470b834fe
555089fdfc37      bpftool: Fix printing incorrect pointer in btf_dump_ptr           22c349e8db89
d380dcde9a07      tracing: Fix now invalid var_ref_vals assumption in trace action  8bcebc77e85f
bef69dd87828      sched/cpufreq: Move the cfs_rq_util_change() call to cpufreq_upd  039ae8bcf7a5
```

Output is a table that summarizes the potential missing commits. In the above example, column names 'Missing_commit' and 'Missing_commit_summary' refer the upstream commit that appear missing from v4.19 based on v5.4. Column 'Based_on_commit' is the upstream commit that was fixed or reverted in v5.4, and that is also included in v4.19. In addition to the table to stdout, the script generates a CSV file with more details for the found missing commits.

Note that the produced list of missing patches requires manual effort to determine if the found missing patches would actually be relevant in the branch specified by CSV1. You may want to use the option `--blacklist` to specify a list of upstream commits that should not be applied to branch specified by CSV1. Blacklist file is simply a text file that lists the upstream commit hexshas for the blacklisted commits. For instance, if you want to ignore ca9033ba69c7 and f667216c5c7c when determining the missing commits from v4.19 based on v5.4, you could have the following contents in a text file:

```
$ cat blacklist_v5.4-v4.19.txt

# Blacklist can include text too. Only string sequences that
# look like git commit hexshas ([0-9a-f]{10,40}) are considered
# blacklist elements:
f667216c5c7c
ca9033ba69c7e3477f207df69867b2ea969197c8
```

and then run the xrefmissing.py with --blacklist option:
```
$ ./xrefmissing.py --blacklist blacklist_v5.4-v4.19.txt v4.19.csv v5.4.csv
```

Also note that xrefmissing.py can be used to find commits that appear missing from the stable tree compared to any other kernel tree. In the above example, we compared v4.19 to v5.4 stable tree. However, the script can be used to compare a stable tree to any other kernel tree, for instance: to another stable tree, stable-rc tree, the mainline tree, or the linux-next tree.

Indeed, there might be different uses for the tool depending on the compared kernel trees. As an example, below are some foreseen use-cases:
* Comparing the target stable tree to another stable tree would yield missing patches potential for backporting from mainline to the target stable tree, based on the patches having already been deemed stable material for the other stable tree.
* Comparing the stable-rc tree to linux-next tree would yield patches pending in linux-next that fix an issue in some of the patches included in the specified stable-rc. You may want to consider holding back the quoted stable-rc commits until they can be backported together with the identified missing commit.
* Comparing the stable-rc tree to mainline tree would yield patches already in mainline linux that fix an issue in some of the patches included in the specified stable-rc. You may want to consider either holding back the quoted stable-rc commits until they can be backported together with the identified missing commit, or in some cases, you may want to consider backporting the mainline commit immediately together with the quoted stable-rc commit.


## Finding Missing Commits Using a Helper Script
[find-missing-commits.py](find-missing-commits.py) is a simple front-end to xrefdb.py and xrefmissing.py to make it easier to update the list of potentially missing commits from stable releases based on pre-defined revision ranges. Given a path to linux-stable git repository (`--stable`) and another linux repository (`--other`), this script calls xrefdb.py and xrefmissing.py to find commits potentially missing from stable tree based on commits in the other kernel tree.

You may want to modify the checked revision ranges by editing the CHECKLIST array defined at the top of the script. By default, the script checks for missing fixes from stable branches v5.4 and v4.19 based on commits in linux-next pending-fixes branch (i.e. the default CHECKLIST configuration assumes `--other` specifies a linux-next repository):

```
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

```

Below is an example of running the script using linux-stable-rc and linux-next repositories:

```
$ ./find-missing-commits.py --stable ~/linux-stable-rc --other ~/linux-next

[+] Reading commit history, this might take a few minutes
[+] stable-v5.4.csv appears to be missing the below commits based on commits in linux-next_v5.4_pending-fixes.csv:

Missing_commit    Missing_commit_summary                                            Based_on_commit
----------------  ----------------------------------------------------------------  -----------------
0bcd7762727d      x86/iopl: Make 'struct tss_struct' constant size again            05b042a19443
51bfb1d11d6d      futex: Fix kernel-doc notation warning                            3ef240eaff36
b73b7f48895a      Revert "drm/amd/display: setting the DIG_MODE to the correct val  967a3b85bac9
68a33b179466      dma-direct: exclude dma_direct_map_resource from the min_low_pfn  b12d66278dd6
1d8006abaab4      bpf: Fix cgroup ref leak in cgroup_bpf_inherit on out-of-memory   e10360f815ca
317a8d9eb612      drm/amdgpu: remove redundant variable r and redundant return sta  de7b45babd9b
f1ed10264ed6      vti[6]: fix packet tx through bpf_redirect() in XinY cases        95224166a903
0d1c3530e1bd      net_sched: keep alloc_hash updated after hash allocation          599be01ee567
3907ccfaec5d      crypto: atmel-aes - Fix CTR counter overflow when multiple fragm  781a08d9740a

[+] stable-v4.19.csv is missing the below commits based on commits in linux-next_v5.4_pending-fixes.csv:

Missing_commit    Missing_commit_summary                                            Based_on_commit
----------------  ----------------------------------------------------------------  -----------------
01091c496f92      acpi/nfit: improve bounds checking for 'func'                     11189c1089da
cf17a1e3aa1a      ARM: 8942/1: Revert "8857/1: efi: enable CP15 DMB instructions b  e17b1af96b2a
ca9033ba69c7      IB/hfi1: Don't cancel unused work item                            4d43d395fed1
8d82cee2f8aa      pstore: Make pstore_choose_compression() static                   cb095afd4476
f667216c5c7c      mmc: sdhci-of-esdhc: re-implement erratum A-009204 workaround     5dd195522562
dc8d37ed304e      cpu/SMT: Fix x86 link error without CONFIG_SYSFS                  ec527c318036
c05b9d7b9f3e      media: fdp1: Fix R-Car M3-N naming in debug message               4e8c120de926
069e47823fff      bnx2x: Enable Multi-Cos feature.                                  d1f0b5dce8fd
fb3c06cfda0d      iwlwifi: fw: make pos static in iwl_sar_get_ewrd_table() loop     ba3224db7803
dde9f095583b      afs: Fix handling of an abort from a service handler              2067b2b3f484
c034f2aa8622      KVM: VMX: Fix conditions for guest IA32_XSS support               4d763b168e9c
e19ecbf105b2      ASoC: sgtl5000: Fix VDDA and VDDIO comparison                     b6319b061ba2
1489d1794001      Revert "drm/radeon: Fix EEH during kexec"                         6f7fe9a93e6c
e80d89380c5a      docs: admin-guide: Remove threads-max auto-tuning                 b0f53dbc4bc4
23f61b9fc5cc      EDAC/ghes: Fix locking and memory barrier issues                  1e72e673b9d1
d18580b08b92      drm/i915: make pool objects read-only                             4f7af1948abc
396d2e878f92      kvm: x86: Host feature SSBD doesn't imply guest feature SPEC_CTR  0c54914d0c52
11dd34f3eae5      powerpc/pseries: Drop pointless static qualifier in vpa_debugfs_  c6c26fb55e8e
612eb1c3b9e5      Revert "net: bcmgenet: use RGMII loopback for MAC reset"          3a55402c9387
e9f930ac88a8      iomap: fix return value of iomap_dio_bio_actor on 32bit systems   4721a6010990
24885d1d79e2      KVM: x86: Remove a spurious export of a static function           cbbaa2727aa3
6fedae3cad8b      ata: brcm: fix reset controller API usage                         2b2c47d9e1fe
eb014de4fd41      netfilter: nf_tables: autoload modules from the abort path        ec7470b834fe
555089fdfc37      bpftool: Fix printing incorrect pointer in btf_dump_ptr           22c349e8db89
d380dcde9a07      tracing: Fix now invalid var_ref_vals assumption in trace action  8bcebc77e85f
f1ed10264ed6      vti[6]: fix packet tx through bpf_redirect() in XinY cases        95224166a903
0d1c3530e1bd      net_sched: keep alloc_hash updated after hash allocation          599be01ee567
3907ccfaec5d      crypto: atmel-aes - Fix CTR counter overflow when multiple fragm  781a08d9740a
bef69dd87828      sched/cpufreq: Move the cfs_rq_util_change() call to cpufreq_upd  039ae8bcf7a5

[+] Done, for more details, see: ~/xref-tool/missing_fixes
```

## License
This project is licensed under the GPL 2.0 license - see the [GPL-2.0-only.txt](LICENSES/GPL-2.0-only.txt) file for details.
