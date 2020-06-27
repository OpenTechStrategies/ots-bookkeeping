#!/usr/bin/env python3

"""Reconcile tools for making the ledger match the statements.

"""

import click
import util as u
import register
import threadfin_beancount as beancount
import pprint
from money import Money
import mustache
import datetime
from dateutil import parser as dateparse
import collections
import subprocess
import re
import pystache
import os
import sys


# import tdbank
pp = pprint.PrettyPrinter(indent=4).pprint


class Account(dict):
    def __init__(self, account):
        dict.__init__(self, account)
        self['reg'] = beancount.get_register(self)
        self['txs'] = self['reg'].get_txs()
        self.winnow_entries()
        self.calc_dailies()

    def date_txs(self, date):
        """Return a list of transactions on DATE that hit accounts we care about"""

        ret = [tx for tx in self['reg'].get_txs(date)
               if tx.hits_accounts(self['ledger_accounts'])]
        for tx in ret:
            tx.calc_amount(self['ledger_accounts'])
        return ret

    def indexable(self, date):
        """Get all the transactions from DATE, sort them, and return them as
        an Indexable.

        This will let us manage the list of sorted transactions with a
        little more control than just iterating over them.  We can,
        for example, more easily iterate over two indexables at once.

        """
        return u.Indexable(
            sorted(
                self.date_txs(date),
                key=lambda k: k['amount'],
                reverse=True))

    def winnow_entries(self):
        """Winnow entries that don't touch the checking account.  For ones
        that do, calculate and set amounts for each transaction.

        """
        self['txs'] = [tx for tx in self['txs']
                       if tx.hits_accounts(self['ledger_accounts'])]
        for e in self['txs']:
            e.calc_amount(self['ledger_accounts'])

    def calc_dailies(self):
        """Calc a running total, which we can do because the entries are
        sorted by date.

        """

        total = 0
        self['dailies'] = {}
        for tx in self['txs']:
            total = tx['total_to_date'] = total + tx['amount']
            self['dailies'][tx.tx.date] = total


class Reconciler():
    def __init__(self, ac1, ac2):
        self.ac1 = Account(ac1)
        self.ac2 = Account(ac2)

    def get_latest_good_date(self):
        """Returns two values: the latest date on which both ledgers match and
        the earliest day on which they don't match."""
        curr_day = datetime.datetime.today().date()
        earliest_bad_date = curr_day
        curr_day += datetime.timedelta(1)

        while curr_day >= self.ac1['txs'][0].tx.date:
            curr_day -= datetime.timedelta(1)

            # If this day isn't in either ledger, try another day
            if not (curr_day in self.ac1['dailies'] or
                    curr_day in self.ac2['dailies']):
                continue

            # If this day is in both ledgers and the amounts are equal,
            # we've found the latest good day.
            if (curr_day in self.ac1['dailies'] and curr_day in self.ac2['dailies']
                    and self.ac1['dailies'][curr_day] == self.ac2['dailies'][curr_day]):
                return(curr_day, earliest_bad_date)

            earliest_bad_date = curr_day

        return (None, earliest_bad_date)

    def reconcile(self, date=""):
        """Reconcile our two accounts and make a webpage with differences for
        first bad date"""

        latest_good, earliest_bad = self.get_latest_good_date()
        if not latest_good:
            print("There are no days on which the statement and the bank account match.")
            return
        print(
            "The last date on which the statement and the daily balance line up is: %s" %
            latest_good)

        print("Next transaction: %s" % earliest_bad)
        self.write_web_page("out.html", earliest_bad)

    def web_page(self, date):
        rows = []
        tx1 = self.ac1.indexable(date)
        tx2 = self.ac2.indexable(date)

        while(not tx1.done() or not tx2.done()):
            row_class = "rowEven" if len(rows) % 2 == 0 else "rowed"
            if tx1.done():
                col1 = '<font color="red">%s</font>' % tx2.curr().as_beancount()
                col2 = tx2.curr().html
                tx2.next()
            elif tx2.done():
                col1 = tx1.curr().html
                col2 = '<font color="red">%s</font>' % tx1.curr().as_beancount()
                tx1.next()
            elif tx1.curr()['amount'] == tx2.curr()['amount']:
                col1 = tx1.curr().html()
                col2 = tx2.curr().html()
                tx1.next()
                tx2.next()
            elif tx1.curr()["amount"] > tx2.curr()["amount"]:
                col1 = tx1.curr().html()
                col2 = '<font color="red">%s</font>' % tx1.curr().as_beancount()
                tx1.next()
            elif tx2.curr()["amount"] > tx1.curr()["amount"]:
                col1 = '<font color="red">%s</font>' % tx2.curr().as_beancount()
                col2 = tx2.curr().html()
                tx2.next()
            dat = {'row_class': row_class,
                   'col1': col1,
                   'col2': col2}
            rows.append(dat)

        # Render and write it out
        body_dat = {'date': date,
                    'col1_total': sum([tx['amount'] for tx in tx1]),
                    'col2_total': sum([tx['amount'] for tx in tx2]),
                    'rows': rows,
                    }

        return mustache.render(
            settings['templates'], "master", {
                'body': mustache.render(
                    settings['templates'],
                    "reconcile_body", body_dat)})

    def write_web_page(self, fname, date):
        account = ""
        # Write web page
        with open(fname, 'w') as fh:
            fh.write(self.web_page(date))


@click.command()
@click.option('--config', default="config.yaml", help="config file")
@click.option(
    '--date',
    default="",
    help="Check one day's transactions against bank records")
@click.argument('account', nargs=2)
def cli(account, config=None, date=""):
    """reconcile - display unreconciled statements between two accounts.

    ACCOUNT is the name of the account in config. Please specify two accounts."""

    global settings
    settings = u.get_config(config)
    beancount.settings = settings
    accounts = {k['name']: k for k in settings['accounts']}

    # Set ledger_accounts in settings.  In config, we keep this info
    # in a different dict so that we can set ledger accounts depending
    # on which two accounts we are reconciling.
    for r in settings['reconcile']:
        if account[0] in r and account[1] in r:
            accounts[account[0]]['ledger_accounts'] = r[account[0]]
            accounts[account[1]]['ledger_accounts'] = r[account[1]]

    reconciler = Reconciler(accounts[account[0]], accounts[account[1]])
    if date:
        reconciler.reconcile(date)
    else:
        reconciler.reconcile()


if __name__ == "__main__":
    cli()
