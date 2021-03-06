#!/usr/bin/env python3

"""Reconcile tools for making the ledger match the statements.

"""

import datetime
import os
import pprint
from typing import Any, Dict, List, Optional, Tuple, Union

import click

import mustache
import threadfin_beancount as beancount
import util as u

pp = pprint.PrettyPrinter(indent=4).pprint


class Account(Dict[str, Any]):
    """This is a dict.  It has some fields that let it represent an account.

    ledger_accounts -=> Assets:Checking etc
    ledger_fname -=> The name of the beancount file
    name -=> A string like 'main' or 'chase' that is the name of this account
    reg -=> the beancount register for this account
    txs -=> the transactions in that register

    """

    def __init__(self, account: Dict[str, Any]) -> None:
        dict.__init__(self, account)
        self["reg"] = beancount.get_register(self)
        self["txs"] = self["reg"].get_txs()
        self.winnow_entries()
        self.calc_dailies()

    def date_txs(self, date: datetime.date) -> List[beancount.Transaction]:
        """Return a list of transactions on DATE that hit accounts we care about"""

        ret = [
            tx
            for tx in self["reg"].get_txs(date)
            if tx.hits_accounts(self["ledger_accounts"])
        ]
        for tx in ret:
            tx.calc_amount(self["ledger_accounts"])
        return ret

    def indexable(self, date: datetime.date) -> u.Indexable:
        """Get all the transactions from DATE, sort them, and return them as
        an Indexable.

        This will let us manage the list of sorted transactions with a
        little more control than just iterating over them.  We can,
        for example, more easily iterate over two indexables at once.

        """
        return u.Indexable(
            sorted(self.date_txs(date), key=lambda k: k["amount"], reverse=True)
        )

    def get_similar_txs(self, tx) -> List:
        """Return transactions similar to tx."""

        ret = []
        for t in self["reg"].get_txs():
            if t.tx.date < tx.tx.date or not t.hits_accounts(self["ledger_accounts"]):
                continue
            t.calc_amount(self["ledger_accounts"])
            if tx["amount"] == t["amount"]:
                ret.append(t.as_beancount())
                ret.append(t.html())
                continue
        return ret

    def winnow_entries(self) -> None:
        """Winnow entries that don't touch the checking account.  For ones
        that do, calculate and set amounts for each transaction.

        """
        self["txs"] = [
            tx for tx in self["txs"] if tx.hits_accounts(self["ledger_accounts"])
        ]
        for e in self["txs"]:
            e.calc_amount(self["ledger_accounts"])

    def calc_dailies(self) -> None:
        """Calc a running total, which we can do because the entries are
        sorted by date.

        """

        total = 0
        self["dailies"] = {}
        for tx in self["txs"]:
            total = tx["total_to_date"] = total + tx["amount"]
            self["dailies"][tx.tx.date] = total


class Reconciler:
    def __init__(
        self,
        ac1: Dict[str, Union[str, List]],
        ac2: Dict[str, Union[str, List]],
        templates: Dict[str, str],
    ) -> None:
        self.ac1 = Account(ac1)
        self.ac2 = Account(ac2)
        self.templates = templates

    def get_latest_good_date(self) -> Tuple[Optional[datetime.date], datetime.date]:
        """Returns two values: the latest date on which both ledgers match and
        the earliest day on which they don't match."""
        curr_day = datetime.datetime.today().date()
        earliest_bad_date = curr_day
        curr_day += datetime.timedelta(1)

        while curr_day >= self.ac1["txs"][0].tx.date:
            curr_day -= datetime.timedelta(1)

            # If this day isn't in either ledger, try another day
            if not (curr_day in self.ac1["dailies"] or curr_day in self.ac2["dailies"]):
                continue

            # If this day is in both ledgers and the amounts are equal,
            # we've found the latest good day.
            if (
                curr_day in self.ac1["dailies"]
                and curr_day in self.ac2["dailies"]
                and self.ac1["dailies"][curr_day] == self.ac2["dailies"][curr_day]
            ):
                return (curr_day, earliest_bad_date)

            earliest_bad_date = curr_day

        return (None, earliest_bad_date)

    def reconcile(self, date: str = "") -> None:
        """Reconcile our two accounts and make a webpage with differences for
        first bad date"""

        latest_good, earliest_bad = self.get_latest_good_date()
        if not latest_good:
            print(
                "There are no days on which the statement and the bank account match."
            )
            return
        print(
            "The last date on which the statement and the daily balance line up is: %s"
            % latest_good
        )

        print("Next transaction: %s" % earliest_bad)
        self.write_web_page("/tmp/reconcile.html", earliest_bad)

    def web_page(self, date: datetime.date) -> str:
        rows = []  # type: List[Dict[str,str]]
        tx1 = self.ac1.indexable(date)
        tx2 = self.ac2.indexable(date)

        while not tx1.done() or not tx2.done():
            row_class = "rowEven" if len(rows) % 2 == 0 else "rowed"
            top = True  # add to top of page?
            if tx1.done():
                print("col 1 done")
                col1 = "<br>".join(self.ac1.get_similar_txs(tx2.curr()))
                col2 = '<font color="red">%s</font>' % tx2.curr().as_beancount()
                col2 += tx2.curr().html()
                tx2.next()
            elif tx2.done():
                print("col 2 done")
                col1 = '<font color="red">%s</font>' % tx1.curr().as_beancount()
                col1 += f"<br />{tx1.curr().html()}"
                col2 = "<br>".join(self.ac2.get_similar_txs(tx1.curr()))
                tx1.next()
            elif tx1.curr()["amount"] == tx2.curr()["amount"]:
                print("col1 == col2")
                top = False
                col1 = tx1.curr().html()
                col2 = tx2.curr().html()
                tx1.next()
                tx2.next()
            elif tx1.curr()["amount"] > tx2.curr()["amount"]:
                print("col1 > col2")
                col1 = '<font color="red">%s</font>' % tx1.curr().as_beancount()
                col1 += f"<br />{tx1.curr().html()}"
                col2 = "<br>".join(self.ac2.get_similar_txs(tx1.curr()))
                tx1.next()
            elif tx1.curr()["amount"] < tx2.curr()["amount"]:
                print("col1 < col2")
                col1 = tx2.curr().html()
                col1 = "<br>".join(self.ac1.get_similar_txs(tx2.curr()))
                col2 = '<font color="red">%s</font>' % tx2.curr().as_beancount()
                tx2.next()
            dat = {"row_class": row_class, "col1": col1, "col2": col2}

            # Add matched transactions to the bottom of the page, and
            # unmatched to the top, so they'll get noticed easier and
            # not require scrolling.
            if top:
                rows = [dat] + rows
            else:
                rows.append(dat)

        # Render and write it out
        body_dat = {
            "date": date,
            "col1_total": sum([tx["amount"] for tx in tx1]),
            "col2_total": sum([tx["amount"] for tx in tx2]),
            "rows": rows,
        }

        body = mustache.render(self.templates, "reconcile_body", body_dat)
        return mustache.render(self.templates, "master", {"body": body})

    def write_web_page(self, fname: str, date: datetime.date) -> None:
        # Write web page
        with open(fname, "w") as fh:
            fh.write(self.web_page(date))


@click.command()
@click.option("--config", help="config file")
@click.option("--date", help="Check a day's transactions against bank records")
@click.option("--templates", help="Template directory")
@click.argument("account", nargs=2)
def cli(
    account: List[str], config: str = "", date: str = "", templates: str = ""
) -> None:
    """reconcile - display unreconciled statements between two accounts.

    ACCOUNT is a beancount file.  Please specify two."""

    # Load templates
    if not templates:
        templates = os.path.join(os.path.split(__file__)[0], "templates")
    template_dict = mustache.load_templates(templates)

    beancount.settings = {"templates": template_dict}

    settings = u.get_config(config)
    accounts = {k["name"]: k for k in settings["accounts"]}

    # Set ledger_accounts in settings.  In config, we keep this info
    # in a different dict so that we can set ledger accounts depending
    # on which two accounts we are reconciling.
    for r in settings["reconcile"]:
        if account[0] in r and account[1] in r:
            accounts[account[0]]["ledger_accounts"] = r[account[0]]
            accounts[account[1]]["ledger_accounts"] = r[account[1]]

    reconciler = Reconciler(
        accounts[account[0]], accounts[account[1]], templates=template_dict
    )
    if date:
        reconciler.reconcile(date)
    else:
        reconciler.reconcile()


if __name__ == "__main__":
    cli()
