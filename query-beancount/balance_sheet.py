"""
qb balance-sheet FOO.ltx YEAR generates a LaTeX balance sheet for YEAR and names it FOO.ltx

FOO.ltx defaults to balance-sheet.ltx
YEAR defaults to last year.

Try this:

./qb balance-sheet ${OTS_DIR}/finances/taxes/2018/ots-balance-sheet-2018-12-31.ltx
"""

import datetime
import os
import sys
from typing import List

import click
from moneyed import Money  # type: ignore

import util as u
from income_statement import Accounts

account_names = {
    "Assets:Checking": "Checking Account",
    "Assets:Guaranteed-Payments": "",
    "Assets:Client-Reimbursable-Expenses": "Client-Reimbursable Expenses",
    "Assets:Receivable": "Receivable",
    "Liabilities:Payable:James": "Payable to James Vasile",
    "Liabilities:Payable:Karl": "Payable to Karl Fogel",
}


OTS_DIR = ""
BEAN_FILE = ""


class Table(list):
    def __init__(self, title, entries=None) -> None:
        """Represent a financial statement latex table for the ENTRIES

        TITLE is what we'll call the list

        ENTRIES is a list of pairs: (description, amount)
        """
        self.title = title.upper()
        list.__init__(self)
        if entries:
            self.extend(entries)

    def format_money(self, m: Money) -> str:
        return u.format_money(m).replace("$", r"\$")

    def total(self, divide: int = 1, penny: bool = False):
        """Total the entries and return the result divided by DIVIDE.

        If PENNY is true, we'll round up if there's and thousands,
        else we round down."""

        s = u.sum([s[1] for s in self])
        portion = float(s.amount) / divide
        if portion * 100 != int(portion * 100):
            if penny:
                portion = int(portion * 100) / 100 + 0.01
            else:
                portion = int(portion * 100) / 100
        return u.parse_money(portion)

    def latex(self) -> str:
        "Return a string containing a latex representation of this table."

        ret = []
        ret.append(r"\begin{longtable}{ l  l  l  r}")
        ret.append(r"  %s \\" % self.title)
        total = u.parse_money(0)
        for e in self:
            total += e[1]
            ret.append(r"  ~~~~~%s & %s \\" % (e[0], self.format_money(e[1])))
        ret.append(r"  \hline")
        ret.append(r"  ~~~~~TOTAL %s & %s \\" % (self.title, self.format_money(total)))
        ret.append(r"\end{longtable}")
        return "\n".join(ret) + "\n"


# Add a get_table method to Accounts


def get_table(accounts: List[str], title: str) -> Table:
    ret = Table(title)
    ret.subtotal = 0
    for account in accounts:
        if account_names.get(account["name"], None) != "":
            ret.subtotal += account["amount"]
            ret.append(
                (account_names.get(account["name"], account["name"]), account["amount"])
            )
    return ret


Accounts.get_table = get_table


@click.command()
@click.argument("output", default="balance-sheet.ltx")
@click.argument("year", default=datetime.datetime.now().year - 1)
def balance_sheet(output: str, year: int) -> None:
    """Generate a balance sheet latex file

    OUTPUT is the latex file to make

    YEAR is the year the balance sheet should cover"""
    this_dir = os.path.abspath(os.path.split(__file__)[0])
    template = u.get_latex_jinja_template(
        os.path.join(this_dir, "letterhead.jinja.ltx")
    )
    title = r"Consolidated Statement of Finance Position for\\Open Tech Strategies, LLC"
    subtitle = "as of COB %s-12-31" % year

    # accounts = Accounts.query("select account, cost(sum(position)) from open on %s-01-01 close on %s-01-01 group by account order by account" % (year, year+1))
    accounts = Accounts.query(
        BEAN_FILE,
        "select account, cost(sum(position)) from date < %s-01-01 group by account order by account"
        % (year + 1)
    )

    assets = accounts.subset("Assets").get_truncated(1)
    assets_table = assets.get_table("Assets")

    liabilities = accounts.subset("Liabilities:Payable").get_truncated(2)
    for account in liabilities:
        account["amount"] = account["amount"] * -1
    liabilities_table = liabilities.get_table("Liabilities")

    equity_table = Table("Equity")
    equity_table.append(("James Vasile", assets_table.total(2, True)))
    equity_table.append(("Karl Fogel", assets_table.total(2, False)))

    out = []
    out.append(assets_table.latex())
    out.append(liabilities_table.latex())
    out.append(equity_table.latex())
    print("Writing %s" % output)
    with open(output, "w") as fh:
        fh.write(template.render(body="\n".join(out), title=title, subtitle=subtitle))
