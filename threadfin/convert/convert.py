#!/usr/bin/env python3

"""# Convert Statements To Beancount
Convert bank satements to beancount data files.

This script looks in the directory or directories supplied on the
command line, then tries to parse %Y%Y%Y%Y_%M%M.pdf files in that dir
as bank statements.  It puts monthly beancount files, one for each
statement in the dir and also puts "all.beancount" there that has all
the transactions found in those statements.  It also leaves monthly
.txt files, which might be useful if grepping for a transaction.

We should stop trying to manage a bunch of bank statement files and
instead just treat them as ledger.  This code does that.

Try this:  bin/threadfin convert ${OTSDIR}/finances/statements

This script does a few sanity checks.  First, it runs a series of
sanity checks on the statement import to make sure things add up.  For
example, all the transactions should add up to the difference between
open and closing balance.  Second, the beancount file gets daily
balance assertions.  Third, we run bean-check on the final output
files.  If all those pass, hopefully that means we have done this more
or less correctly.

In transaction.py, there are two variables of interest.  One is
payee_xlation, which lets you specify how to split common credit card
expenses (e.g. our Amazon AWS bill) and the other is cardholders,
which lets you specify who has which debit card.

"""

import click
import datetime
import os
import re
import sys
import yaml
try:
    import yaml.CLoader
    import yaml.CDumper
    yaml.Loader = yaml.CLoader
    yaml.Dumper = yaml.CDumper
except ImportError:
    pass

import util as u


class UnimplementedError(Exception):
    pass


class Statements(dict):
    """Model bank statements.

    This class is a dict, where keys are YYYY_MM and they hash to Statement objects.

    We rely on bank-name.py having a Statement class tailored to each individual bank.
    """

    def __init__(self, dirname, custom):
        """DIRNAME is a directory that holds a cache of statement pdfs from a bank

        CUSTOM is a data structure that lets us customize the data
        import.  For example, it could let us identify the people
        associated with credit card numbers.  Each bank's parser can
        use it differently.

        """
        self.statements_dir = dirname
        self.custom = custom
        self.get_loaders()

        self.threadfin = {'statements': {'type': "pdf"}}
        threadfin_fname = os.path.join(self.statements_dir, "threadfin.yaml")
        if os.path.exists(threadfin_fname):
            ty = u.get_threadfin_yaml(threadfin_fname)
            self.threadfin.update(ty)

        dict.__init__(self)

    def get_txns(self, date=None):
        """Return all the transactions from all the statements in a list.

        If DATE is specified as a date object, we'll only return transactions from that date."""
        ret = []
        for statement in sorted(self):
            ret.extend(
                [txn for txn in self[statement].transactions if txn['date'] == date])
        return ret

    def get_loaders(self):
        """Any file that has a class that inherits from statement.Statement is
        a parser for a type of statement."""

        direc, fname = os.path.split(__file__)
        fnames = u.run_command(
            "grep -l ^class.*statement.Statement %s/*.py" %
            direc).strip().split("\n")

        # Strip this file from the list of results, trim down to just
        # fname, strip path
        self.banks = [os.path.split(d)[1][:-3]
                      for d in fnames if d != os.path.realpath(__file__)]

    def load(self):
        ext = self.threadfin['statements']['type']
        for pdfname in sorted(os.listdir(self.statements_dir)):
            if pdfname[0] in ".#" or not pdfname.endswith(ext):
                continue
            stub = os.path.splitext(pdfname)[0].replace('_', '/')
            fname = os.path.join(self.statements_dir, pdfname)
            for bank in self.banks:
                try:
                    exec("import %s" % bank)
                except ModuleNotFoundError:
                    continue
                self[stub] = eval(bank + ".Statement(fname, self.custom)")
                if self[stub].bank != "":
                    break

            # Report any error
            if self[stub].bank == "":
                u.err(
                    "Error: couldn't match statements to any bank for %s\n" %
                    fname)

            self[stub].parse()

            # This is like running tests on live data. It has caught
            # so many mistakes.
            self[stub].sanity_check()

    def printable_assertions(self):
        """Return a string with balance assertions we can stick into beancount file"""
        ret = ""
        for _, statement in sorted(self.items()):
            ret += statement.balance_assertions()
        return ret


def get_custom(direc):
    """Load the threadfin.yaml from directory direc

    We'll pass this file to the statement, and each statement can
    write code to do whatever it wants with this yaml data.

    """
    custom = {'accounts': {'debit': 'Assets:Checking', 'credit': 'Expenses'}}
    yaml_fname = os.path.join(direc, "threadfin.yaml")
    if os.path.exists(yaml_fname):
        with open(yaml_fname) as fh:
            custom.update(yaml.load(fh, Loader=yaml.Loader))
    return custom

# This module lets us operate on statements
@click.command()
@click.option('--config', default="config.yaml", help="config file")
@click.argument('directory')
def cli(directory, config=None):
    """Output a statement as a beancount ledger, along with balance assertions."""

    direc = directory

    custom = get_custom(direc)

    statements = Statements(direc, custom)
    statements.load()

    if len(statements.items()) == 0:
        u.err("Couldn't find any statements in %s" % direc)

    # Beancount file frontmatter is stored in the bank-specific
    # modules, so grab the first statement we see just because it
    # has the right info.
    for k, v in statements.items():
        first_statement = v
        break
    ret = first_statement.beanfile_preamble
    ret += first_statement.open_accounts()

    #ret += 'plugin "beancount.plugins.share_postings" "James Karl"\n'
    #ret += 'plugin "beancount.plugins.auto_accounts"\n\n'
    for date in sorted(statements):
        bc = statements[date].write_beancount()
        if bc:
            ret += bc + "\n"

    ret += ("\n;;;;;;;;;;;;;;;;;;;;;;;;\n;; Balance assertions\n")
    ret += (statements.printable_assertions() + "\n")

    beanfile = os.path.join(direc, "all.beancount")
    with open(beanfile, 'w') as fh:
        fh.write(ret)
    if u.run_command("bean-check %s" % beanfile):
        u.err("bean-check has errors for %s" % beanfile)


if __name__ == "__main__":
    cli()
