#!/usr/bin/env python3

import datetime
import os
import sys
import re
import subprocess
from pathlib import Path
from typing import Dict, List

import click
from dateutil import parser as dateparse
import dateutil.parser


def sorted_txs(transactions: str) -> str:
    """Return transactions sorted by date.

    TRANSACTIONS is a string that contain a portion of a ledger
    file with entries in it and nothing else.

    Sort the entries and return a string with them sorted.
    """
    txs_sorted: Dict[datetime.datetime, List[str]]
    txs_sorted = {}  # keys are dates hashed to lists of txs on that date
    split_txs = transactions.split("\n\n")

    ## Some of our transactions might have blank lines (e.g. in comments) and
    ## they are now spread over multiple items in split_txs.  But we need one
    ## tx per item, so let's consolidate.
    txs = []
    for i in range(0, len(split_txs)):
        if not(split_txs[i].startswith(" ") or split_txs[i].startswith("\t")):
            txs.append(split_txs[i])
        else:
            txs[-1]+="\n\n"+split_txs[i]

    for tx in txs:
        # Get the start of the transaction, skipping comment lines
        try:
            linestart = [l for l in tx.split("\n") if not l.startswith(";")][0].split(" ")[0]
        except IndexError:
            sys.stderr.write("Error: free-floating comment not attached to a transaction.  We can't dateparse it, so we can't sort it.\n\nThe transaction:\n\n")
            sys.stderr.write(tx)
            sys.exit(-1)

        try:
            d = dateparse.parse(linestart)
        except dateutil.parser._parser.ParserError:
            print("Bad tx:", tx)
            print("LS:",linestart)
            raise

        if d not in txs_sorted:
            txs_sorted[d] = []
        txs_sorted[d].append(tx)


    ret = ""
    for d in sorted(txs_sorted.keys()):
        for tx in txs_sorted[d]:
            ret += tx.strip() + "\n\n"
    return ret



def sort_beancount_text(beancount_text: str) -> str:
    """BEANCOUNT_TEXT is the contents of a beancount file

    This func separates starting matter from the rest, then
    passes the rest (i.e. the transactions) to sort_txs for
    sorting.
    """


    ## Figure out what line our first transaction is one
    lines = beancount_text.split("\n")
    for l in range(0, len(lines)):
        line = lines[l]
        linestart = line.split(" ")[0]
        try:
            dateparse.parse(linestart)
        except dateutil.parser._parser.ParserError:
            continue
        break

    ## Rewind if there's a comment attached to this transaction
    for i in range(l-1, -1, -1):
        if lines[i].startswith(";"):
            l -= 1
        else:
            break

    # Everything before line l is front matter
    ret = "\n".join(lines[0:l])

    ret += sorted_txs("\n".join(lines[l:]))
    return ret

@click.command()
@click.option("-w", "--write", default=False, is_flag=True)
@click.argument("infile")
def cli(infile: str, write: bool = False) -> None:
    """Sort ledger by effective date.

    We assume a ledger in which the first line of transactions start in column
    0 and that each succeeding line of the transaction is indented with spaces.

    We're going to do this manually rather than use any of data structures
    because we completely avoid any parsing error that might sneak into a
    "parse and reproduce" cycle.

    """
    ret = sort_beancount_text(Path(infile).read_text())
    print(ret)
    if write:
        bak_count = 0
        while os.path.exists(f"{infile}.bak{bak_count}"):
            bak_count += 1
        subprocess.call(f"cp {infile} {infile}.bak{bak_count}", shell=True)
        with open(infile, "w") as fh:
            fh.write(ret)
    else:
        print(ret)


if __name__ == "__main__":
    cli()
