#!/usr/bin/env python3

"""Quick script to generate open/close directives for active accounts

The point of opening and closing accounts is to catch mistakes in
entries going to bogus accounts.  Don't use this unless you're sure
you're current accounts are good.

It won't generate close statements for anything in the current year.

"""

import os
import pprint
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, List, Tuple

import click
from beancount import loader  # type: ignore

import util as u

pp = pprint.PrettyPrinter(indent=4).pprint

if len(sys.argv) < 2:
    u.err("Must specify a beancount file or a dir tree containing beancount files.")


class Accounts(Dict[str, Any]):
    def __init__(self) -> None:
        dict.__init__(self)

    def add(self, account: str, datum: Any) -> None:
        if "James:Karl" in account:
            parts = account.split("James:Karl")
            self.add(f"{parts[0]}James{parts[1]}", datum)
            self.add(f"{parts[0]}Karl{parts[1]}", datum)
        elif "Karl:James" in account:
            parts = account.split("Karl:James")
            self.add(f"{parts[0]}James{parts[1]}", datum)
            self.add(f"{parts[0]}Karl{parts[1]}", datum)
        else:
            if account in self:
                if datum < self[account]["open"]:
                    self[account]["open"] = datum
                if datum > self[account]["close"]:
                    self[account]["close"] = datum
            else:
                self[account] = {"open": datum, "close": datum}


def walk_for_beancount(dirspec: Path) -> List[Path]:
    """Return all beancount files in dir tree DIRSPEC"""
    beancounts = subprocess.check_output(
        f"find {dirspec} -name '*.beancount'", shell=True
    ).decode("UTF-8")
    ret = [Path(e) for e in beancounts.split("\n") if e]
    return ret


def get_beancount_files(beancounts: Tuple[str]) -> List[Path]:
    """Return beancount Path objects and walk dirs for beancount files"""
    ret = []
    for path in [Path(f) for f in beancounts]:
        if os.path.isdir(path):
            ret.extend(walk_for_beancount(path))
        else:
            ret.append(path)
    return ret


@click.command()
@click.argument("beancount", nargs=-1, required=True)
def cli(beancount: Tuple[str]) -> None:
    accounts = Accounts()

    for fspec in get_beancount_files(beancount):
        entries, errors, optiions = loader.load_file(fspec)
        for entry in entries:
            if not hasattr(entry, "postings"):
                continue
            for posting in entry.postings:
                accounts.add(posting.account, entry.date)

    lines = []
    for name, account in accounts.items():
        lines.append(f"{account['open']} open {name}   USD")
        if account["close"].year != date.today().year:
            closing = account["close"] + timedelta(days=1)
            lines.append(f"{closing} close {name}")

    print("2009-01-01 commodity USD")

    lines = sorted(lines)
    for line in lines:
        print(line)


if __name__ == "__main__":
    cli()
