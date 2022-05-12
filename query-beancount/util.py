VERBOSE = False

import datetime
import calendar
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
    """Given a list of position input lines, return a list of the form

      [[amount, date, account, payee],
       [amount, date, account, payee],
       ...etc...,
      ]

    in which amounts are numbers and the rest are strings, and in
    which any given combination of date, partner-combined account, and
    payee only occurs once (i.e., they are combined).

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
        # TECH-DEBT: This code manually reverses the effect of the
        # 'share_postings' plugin, but without consulting the actual
        # line in main.beancount that specifies the sharing, namely,
        # 'plugin "plugins.share_postings" "James Karl"'.  As of
        # 2022-02-25, I've decided I can live with this, but it'll be
        # painful if you remind me of it, so please don't.
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

    If DATE is like YYYY[[/]MM[[/]DD]]-YYYY[[/]MM[[/]DD]], where
    square braces surround optional things, then return a condition
    matching that date range.   For example, "2020-2022/05" would
    become "(date >= 2020-01-01 and date < 2022-06-01)".

    Otherwise, just return DATE and hope it's a legit date."""
    # Hey, if you ever want some inputs to test this with, try these:
    #
    #   2020
    #   2020/05
    #   2020-05
    #   2020/12
    #   2020-12
    #   2020-2022
    #   2020/02-2022
    #   2020/02/01-2022
    #   2020/02/10-2022
    #   2020/02/28-2022
    #   2020/02/29-2022
    #   2018-2020
    #   2018-2020/02
    #   2018-2020/02/01
    #   2018-2020/02/10
    #   2018-2020/02/28
    #   2018-2020/02/29
    #   2018/05/01-2020
    #   2018/05/15-2020/02
    #   2018/05/30-2020/02/01
    #   2018/05/31-2020/02/10
    #   2018/06/01-2020/02/28
    #   2018/12-2020/02/29
    #   2018/12/30-2020/02/29
    #   2018/12/31-2020/02/28
    #   2018/12/31-2020/02/29
    #   2018/05/01-2021
    #   2018/05/15-2021/02
    #   2018/05/30-2021/02/01
    #   2018/05/31-2021/02/10
    #   2018/06/01-2021/02/28
    #   2018/12-2021/02/29
    #   2018/12/30-2021/02/29
    #   2018/12/31-2021/02/28
    #   2018/12/31-2021/02/29
    #   2018/12/31-2021/0228
    #   2018/12/31-2021/0228
    #   201812/31-2021/0228
    #   2018/1231-202102/28
    #   2018/1231-202102/29
    #   2018/1231-202102/29
    #   2018/1231-202002/29
    #   2018/1231-202102/28
    #   2018/1231-202102/28
    if re.match("^[0-9]{4}$", date):
        return f"(date >= {date}-01-01 and date < {str(int(date) + 1)}-01-01)"
    else:
        beg_year  = None
        beg_month = None
        beg_day   = None
        end_year  = None
        end_month = None
        end_day   = None
        def validate_date(b_y, b_m, b_d, e_y, e_m, e_d):
            """Throw a ValueError exception if either date is invalid."""
            try:
                datetime.datetime(year=int(b_y), month=int(b_m), day=int(b_d))
            except ValueError as e:
                raise ValueError(f"date {b_y}/{b_m}/{b_d}: {e}")
            try:
                datetime.datetime(year=int(e_y), month=int(e_m), day=int(e_d))
            except ValueError as e:
                raise ValueError(f"date {e_y}/{e_m}/{e_d}: {e}")
        if m := re.match("^([0-9]{4})[-/]?([0-9]{2})$", date):
            beg_year = m.group(1)
            beg_month = m.group(2)
            beg_day = "01"
            end_year = beg_year
            end_month = f"{((int(m.group(2)) % 12) + 1):02}"
            if end_month == "01":  # we crossed a year boundary
                end_year = f"{(int(beg_year) + 1):02}"
            end_day = "01"
            validate_date(beg_year, beg_month, beg_day, end_year, end_month, end_day)
        elif m := re.match("^([0-9]{4})/?([0-9]{2})?/?([0-9]{2})?-([0-9]{4})/?([0-9]{2})?/?([0-9]{2})?$", date):
            beg_year  = m.group(1)
            beg_month = m.group(2)
            beg_day   = m.group(3)
            end_year  = m.group(4)
            end_month = m.group(5)
            end_day   = m.group(6)
            if beg_month is None:
                beg_month = "01"
            if beg_day is None:
                beg_day = "01"
            if end_month is None:
                end_month = "12"
            if end_day is None:
                end_day = f"{(calendar.monthrange(int(end_year), int(end_month))[1]):02}"
            validate_date(beg_year, beg_month, beg_day, end_year, end_month, end_day)
            # Handle the edge cases.
            if end_month == "12":
                if end_day == "31":
                    end_year = f"{(int(end_year) + 1):02}"
                    end_month = "01"
                    end_day = "01"
                else:
                    end_day = f"{(int(end_day) + 1):02}"
            else:
                last_day = f"{(calendar.monthrange(int(end_year), int(end_month))[1]):02}"
                if end_day == last_day:
                    end_month = f"{(int(end_month) + 1):02}"
                    end_day = "01"
                else:
                    end_day = f"{(int(end_day) + 1):02}"
        else:
            # If didn't match any known pattern, then just return the
            # original date as a query condition and hope it's valid.
            return f"(date={date})"
        # Otherwise, build a custom date-range query condition.
        return f"(date >= {beg_year}-{beg_month}-{beg_day} and date < {end_year}-{end_month}-{end_day})"


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
