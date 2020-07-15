#!/usr/bin/env python3

"""Quick script to generate open/close directives for active accounts

The point of opening and closing accounts is to catch mistakes in
entries going to bogus accounts.  Don't use this unless you're sure
you're current accounts are good.

It won't generate close statements for anything in the current year.

"""

from datetime import date, timedelta
import util as u
import os
import subprocess
import sys
import beancount
from beancount import loader
import pprint
pp = pprint.PrettyPrinter(indent=4).pprint

if len(sys.argv) < 2:
    u.err("Must specify a beancount file or a dir tree containing beancount files.")


class Accounts(dict):
    def __init__(self):
        dict.__init__(self)

    def add(self, account, datum):
        if 'James:Karl' in account:
            parts = account.split("James:Karl")
            self.add(f"{parts[0]}James{parts[1]}", datum)
            self.add(f"{parts[0]}Karl{parts[1]}", datum)
        elif 'Karl:James' in account:
            parts = account.split("Karl:James")
            self.add(f"{parts[0]}James{parts[1]}", datum)
            self.add(f"{parts[0]}Karl{parts[1]}", datum)
        else:
            if account in self:
                if datum < self[account]['open']:
                    self[account]['open'] = datum
                if datum > self[account]['close']:
                    self[account]['close'] = datum
            else:
                self[account] = {'open': datum, 'close': datum}


accounts = Accounts()


def walk_for_beancount(dirspec):
    """Return all beancount files in dir tree DIRSPEC"""
    beancounts = subprocess.check_output(
        f"find {dirspec} -name '*.beancount'", shell=True).decode("UTF-8")
    beancounts = [e for e in beancounts.split("\n") if e]
    return beancounts


fspecs = sys.argv[1]
if os.path.isdir(fspecs):
    fspecs = walk_for_beancount(fspecs)
else:
    fspecs = [fspecs]

for fspec in fspecs:
    entries, errors, optiions = loader.load_file(fspec)
    for entry in entries:
        if not hasattr(entry, 'postings'):
            continue
        for posting in entry.postings:
            accounts.add(posting.account, entry.date)

lines = []
for name, account in accounts.items():
    lines.append(f"{account['open']} open {name}   USD")
    if account['close'].year != date.today().year:
        closing = account['close'] + timedelta(days=1)
        lines.append(f"{closing} close {name}")

print("2009-01-01 commodity USD")

lines = sorted(lines)
for line in lines:
    print(line)
