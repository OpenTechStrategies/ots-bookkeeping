#!/usr/bin/env python3

import click
from dateutil import parser as dateparse
import subprocess
import os
import util as u


def sorted_txs(txs):
    """TXS is a string containing a portion of a ledger file with entries in it and nothing else.

    Sort the entries and return value."""
    txs_sorted = {}  # keys are dates hashed to lists of transactions on that effective date
    txs = txs.split("\n\n")
    for tx in txs:
        linestart = tx.split(' ')[0]
        if "=" in linestart:
            # Use effective date if specified
            linestart = linestart.split("=")[1]
        d = dateparse.parse(linestart)
        if d not in txs_sorted:
            txs_sorted[d] = []
        txs_sorted[d].append(tx)

    ret = ""
    for d in sorted(txs_sorted.keys()):
        for tx in txs_sorted[d]:
            ret += tx.strip() + "\n\n"
    return ret


def print_sorted_txs(txs):
    """TXS is a string containing a portion of a ledger file with entries in it and nothing else.

    Sort the entries and output to the screen."""
    print(sorted_txs(txs))


@click.command()
@click.option('-w', '--write', default=False, is_flag=True)
@click.argument('infile')
def cli(infile, write=False):
    """Sort ledger by effective date.

    We assume a ledger in which the first line of transactions start
    in column 0 and that each succeeding line of the transaction is
    indented with spaces and there are no blanks lines in
    transactions.  We also assume that effective dates are specified
    using the "date=date" notation and not bracket notation.

    """

    """We're going to do this manually rather than use any of our data
    structures because we completely avoid any parsing error that
    might sneak into a "parse and reproduce" cycle.

    """

    ret = ""
    txs = ""
    non_tx = ""
    for line in u.slurp(infile).split("\n"):
        linestart = line.split(" ")[0]

        # Skip blanks.  We'll put appropriate blanks in later
        if not line.strip():
            if non_tx:
                non_tx += "\n"
            continue

        if not linestart or not linestart[0] or linestart[0] in " \t":
            # We have an indented line

            # If we're in the middle of a non-tx, just add a blank
            # line to the non-tx so it stays the same.
            if non_tx:
                non_tx += "\n"
                continue

            # If this is just a stray blank line, skip it
            if not txs:
                continue

            # We have a line from a transaction (not the first line)
            txs += line + "\n"
        else:
            # We have a non-indented line
            if "=" in linestart:
                # Use effective date if specified
                linestart = linestart.split("=")[1]
            try:
                d = dateparse.parse(linestart)
            except ValueError:
                if txs:
                    ret += sorted_txs(txs)
                    txs = ""
                non_tx += line + "\n"
                continue

            # If this is a new transaction, print any preceding
            # non-transaction
            if non_tx:
                ret += non_tx + "\n"
                non_tx = ""

            # Save the start of the transaction
            txs += "\n" + line + "\n"

    # Output any remaining items
    if non_tx:
        ret += non_tx + "\n"
        non_tx = ""
    elif txs:
        ret += sorted_txs(txs)
        txs = ""

    # Don't let those gaps grow infinitely
    while "\n\n\n" in ret:
        ret = ret.replace("\n\n\n", "\n\n")

    if write:
        bak_count = 0
        while os.path.exists(f"{infile}.bak{bak_count}"):
            bak_count += 1
        subprocess.call(f"cp {infile} {infile}.bak{bak_count}", shell=True)
        with open(infile, 'w') as fh:
            fh.write(ret)
    else:
        print(ret)


if __name__ == "__main__":
    cli()
