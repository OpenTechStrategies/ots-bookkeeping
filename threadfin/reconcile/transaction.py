import math
import re
from typing import Any, Dict, List, Optional


class Transaction(Dict[Any, Any]):
    """This is the Transaction class used by statement parsers.  It is not
    used by reconcile.  That routine uses the Transaction class in
    threadfin_beancount."""

    def __init__(self, arg: Dict[Any, Any] = {}) -> None:
        dict.__init__(self, arg)

    def dump(self) -> str:
        try:
            note = self["category"] + " " + self["note"]
        except KeyError:
            note = self["category"]
        if self["category"] == "CHECK":
            note += " %d" % self["number"]
        if "type" in self:
            note += " " + self["type"]
        return "{} {:<60}{:>12}\n".format(
            self["date"].strftime("%Y/%m/%d"), note, str(self["amount"])[4:]
        )
        return str(self) + "\n"

    def html(self) -> str:
        category = self["category"]
        if category == "CHECK":
            category += " #%s" % self["number"]
        h = """<div class="statementTx">
{amount}<br>
{category}<br>

<p>{note}</p>
</div>""".format(
            **{
                "amount": self["amount"],
                "category": category,
                "note": self["note"] if "note" in self else "",
            }
        )
        return h

    def as_beancount(self) -> str:
        """Return string with this transaction as a beancount entry."""
        payee = self["note"] if "note" in self else ""
        comment = self["category"] if "category" in self else ""
        narration = ""

        payer = "Karl"
        if payee[-4:] in "4082 ":
            payer = "James"

        payee_xlation = {
            r"^Amazon Web Services Aws.Amazon.CO": [
                "Amazon Web Services",
                "AWS",
                "split",
            ],
            r"^Amtrak .Com ": ["Amtrak", "", ""],
            r"^Amtrak Hotels ": ["Amtrak Hotels", "", ""],
            r"^Digitalocean.Com Digitalocean. NY.*7681": ["Digital Ocean", "", "split"],
            r"^Google \*Gsuite_Opent": ["Google", "", "split"],
            r"^Linode.Com 855-4546633 NJ": ["Linode", "", "split"],
            r"^Lyft \*Ride": ["Lyft", "", ""],
            r"^Rimu Hosting Cambridge": ["Rimu", "", "split"],
            r"^Twilio .* CA ": ["Twilio", "", "split"],
            r"^United [0-9]+ 800.*TX": ["United Airlines", "", ""],
        }

        split = False

        for regex, replacement in payee_xlation.items():
            if re.search(regex, payee):
                comment += " " + payee
                payee = replacement[0]
                narration = replacement[1]
                if replacement[2] == "split":
                    split = True

        if split:
            half = float(self["amount"].amount) / 2.0
            up = math.ceil(half * 100) / 100  # round up
            down = math.floor(half * 100) / 100  # round down
        else:
            up = 0
            down = self["amount"].amount

        if payer == "James":
            up, down = down, up

        h = {
            "date": self["date"],
            "payee": payee,
            "narration": narration,
            "comment": comment,
            "e_karl": down * -1,
            "e_james": up * -1,
            "a_karl": down,
            "a_james": up,
        }
        b = """{date} txn "{payee}" "{narration}"
  comment: "{comment}"
  Expenses:Karl              {e_karl} USD
  Expenses:James             {e_james} USD
  Assets:Checking:Karl       {a_karl} USD
  Assets:Checking:James      {a_james} USD

""".format(
            **h
        )

        b = "\n".join([l for l in b.split("\n") if " 0 USD" not in l])

        with open("generated.beancount", "a") as fh:
            fh.write(b)

        b = b.replace(" ", r"&nbsp;").replace("\n", "<br />\n")
        return b.strip()


class Transactions(List[Transaction]):
    """A list of Transaction instances.

    This is just a list we're wrapping in a class so we can add
    methods to it.

    """

    pass
