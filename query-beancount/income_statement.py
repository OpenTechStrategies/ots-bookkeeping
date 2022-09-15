"""
qb income-statement FOO.ltx YEAR generates a LaTeX income statement for YEAR and names it FOO.ltx

FOO.ltx defaults to income-statement.ltx
YEAR defaults to last year.

Try this:

./qb income-statement ${OTS_DIR}/finances/taxes/2018/ots-income-statement-2018-12-31.ltx
"""

import csv
import datetime
import io
import os
import sys
from typing import (Any, Callable, Dict, Iterable, List, Type, TypeVar, Union,
                    cast)

import click
from moneyed import Money  # type: ignore

import util as u

BEAN_FILE = ""


Account_T = TypeVar("Account_T", bound="Account")


class Account(Dict[str, Union[str, Money]]):
    def __init__(self, name: str, amount: Union[Money, Type[Account_T], float]) -> None:
        dict.__init__(self)
        self["name"] = name
        self["amount"] = u.parse_money(amount)

    def __add__(
        self, other: Union[Money, Type[Account_T], int, float]
    ) -> Type[Account_T]:
        """Returns an Account with A's name but A+B's amount"""
        if not isinstance(other, type(self)):
            other = Account("", other)
        return cast(
            Type[Account_T], Account(self["name"], self["amount"] + other["amount"])
        )

    def __radd__(
        self, other: Union[Money, int, float, Type[Account_T]]
    ) -> Type[Account_T]:
        if other == 0:
            return cast(Type[Account_T], self.copy())
        else:
            return self.__add__(other)

    def __sub__(self, other_account: Type[Account_T]) -> Type[Account_T]:
        """Returns an Account with A's name but A-B's amount"""
        ret = Account(self["name"], self["amount"] - other_account["amount"])
        return cast(Type[Account_T], ret)

    def format_ltx(self) -> Dict[str, str]:
        """Returns a dict, not an Account object"""
        return {
            "name": self["name"],
            "amount": u.format_money(self["amount"], latex=True),
        }


Accounts_T = TypeVar("Accounts_T", bound="Accounts")


class Accounts(List[Account]):
    """Represent a list of account objects."""

    def format_ltx(self) -> List[Dict[str, Union[str, Money]]]:
        return [a.format_ltx() for a in self]

    def get_truncated(self, level) -> Type[Accounts_T]:
        """Return an Accounts object that is a set of account names that
        collapse anything below LEVEL, which is 0-indexed.  If LEVEL
        is 2, this will turn "Liabilities:Payable:James:Solo" and
        "Liabilities:Payable:James:Notional" into
        "Liabilities:Payable:James" and that account will hold the sum
        of the other two.

        """
        ret_d: Dict[str, Account] = {}
        for account in self:
            parts = account["name"].split(":", level + 1)

            # If our account name has enough parts, truncate, else add
            # Misc
            if len(parts) > level + 1:
                name = ":".join(parts[:-1])
            elif len(parts) == level + 1:
                name = account["name"]
            else:
                name = account["name"] + ":Miscellaneous"

            # amount = u.parse_money(account['amount'])
            if name in ret_d:
                ret_d[name] += Account(name, account["amount"])
            else:
                ret_d[name] = Account(name, account["amount"])

        ret = [ret_d[r] for r in sorted(ret_d.keys())]

        return Accounts(ret)

    @classmethod
    def query(cls, bean_file: str, query: str) -> Type[Accounts_T]:
        print(query)
        self = cls()
        # Get account data as a list of dicts
        results = u.bean_query(bean_file, query, csv=True)
        fh = io.StringIO(results)
        reader = csv.DictReader(fh)
        for row in reader:
            if row["cost_sum_position"].strip():
                self.append(
                    Account(
                        row["account"].strip(), u.parse_money(row["cost_sum_position"])
                    )
                )
        return self

    def subset(self, test: Union[str, Callable[[Account], bool]]) -> List[Account]:
        """Return accounts for which TEST returns True.

        TEST is a function that takes an account or else it's a
        string.  If it's a string, the test is account['name'].startswith(test).

        Returns an Accounts object.

        """
        if isinstance(test, str):
            return Accounts([a for a in self if a["name"].startswith(test)])

        return Accounts([a for a in self if test(a)])

    def sum(self, name: str = "") -> Money:
        if name:
            return u.sum(
                [u.parse_money(a["amount"]) for a in self if a["name"].startswith(name)]
            )
        return u.sum([u.parse_money(a["amount"]) for a in self])

    def sum_ltx(self, name: str = "") -> str:
        return u.format_money(self.sum(name), latex=True)

    def transform(self, transformation: Callable[[Account], Account]) -> List[Account]:
        """Apply transformation to every item in self and replace the item in
        self with the transformed item.

        TRANSFORMATION is a function that takes an Account object and
        returns an Account object.

        For convenience, this object returns SELF.

        """
        for i in range(len(self)):
            self[i] = transformation(self[i])
        return self

    def transform_name(self, transformation: Callable[[str], str]) -> List[Account]:
        """Apply transformation to name of every item in self and replace the
        item in self with the transformed item.

        """
        for i in range(len(self)):
            self[i]["name"] = transformation(self[i]["name"])
        return self


def is_expense(name: str = "") -> bool:
    if not name:
        return lambda x: x["name"].startswith("Expenses:")
    else:
        return lambda x: x["name"].startswith("Expenses:%s" % name)


def clip_expense_name(name: str) -> str:
    if name in "Expenses:James Expenses:Karl":
        return "Misc"
    else:
        return ":".join(name.split(":")[2:])


@click.command()
@click.argument("output", default="income-statement.ltx")
@click.argument("year", default=datetime.datetime.now().year - 1)
def income_statement(output: str, year: int) -> None:
    """Generate an income statement latex file

    OUTPUT is the latex file to make

    YEAR is the year the statement should cover"""
    this_dir = os.path.abspath(os.path.split(__file__)[0])
    template = u.get_latex_jinja_template(
        os.path.join(this_dir, "profits-n-losses.jinja.ltx")
    )
    title = r"Profits and Losses of\\Open Tech Strategies, LLC"
    subtitle = "1 January through 31 December %s" % year

    accounts = Accounts.query(
        BEAN_FILE,
        "select account, cost(sum(position)) from open on %s-01-01 close on %s-01-01 group by account order by account"
        % (year, year + 1),
    )

    karl = {}
    james = {}
    james["expenses"] = accounts.subset(is_expense("James"))
    karl["expenses"] = accounts.subset(is_expense("Karl"))

    james["truncated_expenses"] = (
        james["expenses"].get_truncated(2).transform_name(clip_expense_name)
    )
    karl["truncated_expenses"] = (
        karl["expenses"].get_truncated(2).transform_name(clip_expense_name)
    )
    james["guaranteed"] = accounts.subset("Expenses:James:Guaranteed-Payments").sum()
    karl["guaranteed"] = accounts.subset("Expenses:Karl:Guaranteed-Payments").sum()

    out = {"title": title, "subtitle": subtitle, "year": year}

    out["vasile_income"] = u.format_money(-1 * accounts.sum("Income:James"), True)
    out["fogel_income"] = u.format_money(-1 * accounts.sum("Income:Karl"), True)
    income = (
        -1
        * accounts.subset(
            lambda x: x["name"].startswith("Income:James")
            or x["name"].startswith("Income:Karl")
        ).sum()
    )
    out["ots_income"] = u.format_money(income, latex=True)

    out["vasile_expenses"] = james["truncated_expenses"].format_ltx()
    out["vasile_expenses_total"] = james["truncated_expenses"].sum_ltx()
    out["fogel_expenses"] = karl["truncated_expenses"].format_ltx()
    out["fogel_expenses_total"] = karl["truncated_expenses"].sum_ltx()
    expenses = accounts.sum("Expenses")
    out["ots_expenses"] = u.format_money(expenses, latex=True)

    out["vasile_net_income"] = u.format_money(
        -1 * accounts.sum("Income:James") - james["truncated_expenses"].sum(),
        latex=True,
    )
    out["fogel_net_income"] = u.format_money(
        -1 * accounts.sum("Income:Karl") - karl["truncated_expenses"].sum(), latex=True
    )
    out["net_income"] = u.format_money(income - expenses, latex=True)

    out["vasile_guaranteed"] = u.format_money(james["guaranteed"], latex=True)
    out["fogel_guaranteed"] = u.format_money(karl["guaranteed"], latex=True)

    # print(accounts.subset("Assets:Guaranteed-Payments"))
    if (
        accounts.subset(is_expense()).sum()
        != james["expenses"].sum() + karl["expenses"].sum()
    ):
        u.err("Total expenses doesn't equal James's expenses + Karl's!")

    print("Writing %s" % output)
    with open(output, "w") as fh:
        fh.write(template.render(out))
