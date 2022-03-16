VERBOSE = False

import datetime
import os
import re
import subprocess
import sys
import time
from typing import Any, List, Optional, Union

from dateutil import parser as dateparser
from moneyed import Money  # type: ignore


def bean_query(bean_file: str, query: str, csv: bool = False) -> str:
    csv_param = "-f csv" if csv else ""
    cmd = 'bean-query %s %s "%s";' % (csv_param, bean_file, query)
    return run_command(cmd)


def err(msg: str) -> None:
    if not msg.endswith("\n"):
        msg += "\n"
    sys.stderr.write(msg)
    sys.exit(-1)


def format_money(m: Money, latex: bool = False) -> str:
    from moneyed import localization

    ret: str = localization.format_money(m, locale="en_US")
    if latex and "$" in ret:
        ret = ret.replace("$", r"\$")
    return ret


def get_latex_jinja_template(template_fname: str):
    """Given a path to a jinja template, treat it like a latex-specialized
    template, load it, and return the template object.

    """
    import jinja2

    this_dir, template_fname = os.path.split(template_fname)
    this_dir = os.path.abspath(this_dir)
    # Big thanks to http://eosrei.net/articles/2015/11/latex-templates-python-and-jinja2-generate-pdfs
    latex_jinja_env = jinja2.Environment(
        block_start_string="\BLOCK{",
        block_end_string="}",
        variable_start_string="\VAR{",
        variable_end_string="}",
        comment_start_string="\#{",
        comment_end_string="}",
        line_statement_prefix="%%",
        line_comment_prefix="%#",
        trim_blocks=True,
        autoescape=False,
        loader=jinja2.FileSystemLoader(this_dir),
    )
    return latex_jinja_env.get_template(template_fname)


def parse_date(string: str, ignore_error: bool = False) -> Optional[datetime.date]:
    "Return a date object representation of STRING."
    try:

        return dateparser.parse(string).date()
    except ValueError:
        if ignore_error:
            return None
        else:
            raise


# TODO: This may be The Wrong Way to do things?  Surely beancount
# provides a Python library that hands us the objects we want directly
# as our query results, and the printed output from 'bean-query' is
# just a stringification of those objects.  Thus, parsing the output
# of 'bean-query' to get back to an object representation is silly.
# We should just use the objects Beancount can already make for us.
# I'll do some more research and figure this out.  -Karl, 2022-02-25
def parse_positions(lines: list) -> list:
    """Given a list of postion input lines, return a list of this form

      [[amount, date, account, payee],
       [amount, date, account, payee],
       ...etc...,
      ]

    in which amounts are numbers and the rest are strings, and in
    which any given combination of date, partner-combined account, and
    payee only occurs once (i.e., they are combined)

    For example, given input list LINES of strings like this:

      [ "2022-01-14 Expenses:James:Tech  775.00 USD J. Random",
        "2022-01-14 Expenses:Karl:Tech   775.00 USD J. Random",
        "2022-02-09 Expenses:James:Tech  350.00 USD J. Random",
        "2022-02-09 Expenses:Karl:Tech   350.00 USD J. Random",
      ]

    then return this:

      [["2022-01-14", "Expenses:James+Karl:Tech", 1550, "J. Random"],
       ["2022-01-14", "Expenses:James+Karl:Tech",  700, "J. Random"],
      ]
    """

    # Interim hash whose keys are "YYYYMMDD|TOP_LEVEL_ACCT|PAYEE" and
    # whose values are an accumulating amount.
    combos = {}

    for line in lines:
        components = line.split()
        date = components[0]
        acct = components[1]
        # TODO: This is tech debt.  It manually reverses the effect
        # of the 'share_postings' plugin, but without consulting the
        # actual line in main.beancount that specifies the sharing,
        # namely, 'plugin "plugins.share_postings" "James Karl"'.
        # As of 2022-02-25, I've decided I can live with this, but
        # it'll be painful if you remind me of it, so please don't.
        sharing_elision = "..."
        if ":James:" in acct:
            acct = acct.replace(":James:", f":{sharing_elision}:")
        elif ":Karl:" in acct:
            acct = acct.replace(":Karl:", f":{sharing_elision}:")
        amt = float(components[2])
        ignored_currency = components[3]
        payee = " ".join(components[4:]).strip() # klugey, but... shrug
        squished_date = date[0:4] + date[5:7] + date[8:10]
        key = f"{squished_date}|{acct}|{payee}"
        combos[key] = combos.get(key, 0) + amt

    ret_list = []
    for key in combos.keys():
        sqdate, acct, payee = key.split("|")
        total_amt = combos[key]
        unsquished_date = sqdate[0:4] + "-" + sqdate[4:6] + "-" + sqdate[6:8]
        ret_list.append([unsquished_date, acct, total_amt, payee,])

    return ret_list


def date_to_sql_cond(date: str) -> str:
    """Return an SQL 'WHERE' condition that matches DATE.

    DATE is a string expressing a date in some reasonable format.

    If DATE is like YYYY, then return a condition that matches the
    corresponding year.   For example, "2021" would become
    "(date >= 2021-01-01 and date < 2022-01-01)".

    If DATE is like YYYYMM, YYYY/MM, or YYYY-MM, return a condition
    that matches that month.  For example, "2021-02" would become
    "(date >= 2021-02-01 and date < 2021-03-01)".

    Otherwise, just return DATE and hope it's a legit date.

    (Should we implement YYYY[/MM[/DD]]-YYYY[/MM[/DD]] ranges too?)"""
    if re.match("^[0-9]{4}$", date):
        return f"(date >= {date}-01-01 and date < {str(int(date) + 1)}-01-01)"
    elif match := re.match("^([0-9]{4})[-/]?([0-9]{2})$", date):
        y = match.group(1)
        this_m = match.group(2)
        next_m = f"{((int(match.group(2)) % 12) + 1):02}"
        return f"(date >= {y}-{this_m}-01 and date < {y}-{next_m}-01)"
    else:
        return f"(date={date})"


def parse_money(
    money_string: Union[Money, int, str], ignore_error: bool = False
) -> Money:
    """Assumes string is USD, returns money object

    If you pass it an int, it will cast to string.  If you're already
    a Money type, we'll just return what we get.

    """

    if type(money_string) == type(Money(0, "USD")):
        return money_string

    money_string = re.sub("[^-0-9.,$]", "", str(money_string))

    if not ignore_error:
        return Money(amount=money_string, currency="USD")

    try:
        return Money(amount=money_string, currency="USD")
    except ValueError:
        if ignore_error:
            return None
        else:
            raise


def sum(l: List[Any]) -> Any:
    """Sum a list, return the result.

    The sum built-in initializes its accumulator to an int, and when
    we add other types to that int, Python raises a TypeError.  Here,
    we just initialize the accumulator to the first element so it gets
    the type of that element.  This means we return an object of that
    type.

    """
    acc = None
    for i in l:
        if acc == None:
            acc = i
        else:
            acc += i
    return acc


def rm_file(fname: str, verbose: bool = False) -> None:
    """Remove the file unless we're in verbose mode for debugging purposes"""
    if verbose or VERBOSE:
        return
    os.unlink(fname)


class RunCommandError(subprocess.CalledProcessError):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        subprocess.CalledProcessError.__init__(self, *args, **kwargs)
        self.dump()

    def dump(self) -> None:
        sys.stderr.write(self.output)
        sys.stderr.write(self.stderr)
        sys.stderr.write(str(self.returncode))
        sys.stderr.write("\n")


def run_command(cmd: str, verbose: bool = False, ignore_error: bool = False) -> str:
    """Run CMD, return output.  If command returns an error, raise an
    exception that contains the exception string.  If that error isn't
    trapped upstream, print the error and bail.

    CMD is a string containing a command that can be run in a shell.
    """

    if verbose or VERBOSE:
        print(cmd)

    p = subprocess.Popen(
        cmd, shell=True, stderr=subprocess.PIPE, stdout=subprocess.PIPE
    )
    output_bytes, errors_bytes = p.communicate()
    output = output_bytes.decode("UTF-8")
    errors = errors_bytes.decode("UTF-8")

    # Wait until process terminates (without using p.wait())
    while p.poll() is None:
        # Process hasn't exited yet, let's wait some
        time.sleep(0.5)
    return_code = p.returncode

    if return_code != 0 and not ignore_error:
        raise RunCommandError(
            cmd=cmd, returncode=return_code, output=output, stderr=errors
        )
    return output


def slurp(fname: str) -> str:
    with open(fname) as fh:
        return fh.read()
