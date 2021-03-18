#!/usr/bin/env python3
"""Share a posting among a number of participants.

This plugin is given a list of names. It assumes that any posting with
names from that list separated by colons gets split among the listed
names.  It goes through all the transactions and converts all such
postings into multiple postings, one for each member.

For example, given the names 'James' and 'Abdul', the following transaction:

  2015-02-01 * "Aqua Viva Tulum - two nights"
     Income:CreditCard      -269.00 USD
     Expenses:Accommodation:James:Abdul

Will be converted to this:

  2015-02-01 * "Aqua Viva Tulum - two nights"
    Income:James:CreditCard       -269.00 USD
    Expenses:Accommodation:James     134.50 USD
    Expenses:Accommodation:Abdul     134.50 USD

Listing names multiple times will give them multiple shares.  Listing
numbers after names will provide that number of shares for that name.

You can generate reports for a particular person by filtering postings
to accounts with a component by their name.

This plugin is loosely based on Martin Blais's split_expenses plugin.
A few key differences:

 * This plugin can share any posting, not just expenses
 * This plugin requires explicit listing names for every shared posting
 * This plugin can share different postings different ways
 * This plugin lets you specify numbers to share postings in ratios
 * This plugin does not open accounts for you
 * This plugin lets you share account open statements

You probably want to symlink this into a beancount/plugins dir.
"""
__copyright__ = (
    "Copyright (C) 2015-2016  Martin Blais.  Copyright 2018, 2021 James Vasile."
)
__license__ = "GNU GPLv2"

import os
import re
import sys
from typing import Any, Dict, List, Tuple, Union

# If we're running this standalone, we need to import from parent dir
# of this file.
if __name__ == "__main__":
    sys.path.append(os.path.split(os.path.split(os.path.abspath(__file__))[0])[0])


from beancount import loader  # type: ignore
from beancount.core import amount  # type: ignore
from beancount.core import account, account_types, data, getters, interpolate
from beancount.parser import options  # type: ignore
from beancount.query import query, query_render  # type: ignore

__plugins__ = ("share_postings",)


def get_sharing_info(account: str, members: list[str]) -> Tuple[List[str], str]:
    """
    Args:
      account: a string containing a beancount account name
      members: a list of strings of member names

    Returns:
      A list of member names in the account, with members represented
      by their number of shares

    >>> get_sharing_info("Assets:Checking", ["Abdul","James","Stray"])
    ([], '')

    >>> get_sharing_info('Assets:Checking:James', ['Abdul',"James","Stray"])
    ([], '')

    >>> get_sharing_info('Assets:Checking:James:Abdul', ['Abdul',"James","Stray"])
    (['Abdul', 'James'], 'James:Abdul')

    >>> get_sharing_info('Assets:Checking:James:Abdul:Stray', ["Abdul","James","Stray"])
    (['Abdul', 'James', 'Stray'], 'James:Abdul:Stray')

    >>> get_sharing_info("Assets:Checking:James:Abdul:Stray:Foo", ["Abdul","James","Stray"])
    (['Abdul', 'James', 'Stray'], 'James:Abdul:Stray')

    >>> get_sharing_info("Assets:Checking:James:2:Abdul", ["Abdul","James","Stray"])
    (['Abdul', 'James', 'James'], 'James:2:Abdul')

    >>> get_sharing_info("Assets:Checking:James:2:Abdul:Stray:3", ["Abdul","James","Stray"])
    (['Abdul', 'James', 'James', 'Stray', 'Stray', 'Stray'], 'James:2:Abdul:Stray:3')

    >>> get_sharing_info("Assets:Checking:James:2:Abdul:Stray:3:", ["Abdul","James","Stray"])
    (['Abdul', 'James', 'James', 'Stray', 'Stray', 'Stray'], 'James:2:Abdul:Stray:3')

    >>> get_sharing_info('Assets:Checking:James:James:Abdul', ['Abdul',"James","Stray"])
    (['Abdul', 'James', 'James'], 'James:James:Abdul')

    >>> get_sharing_info('Assets:Checking:James:Abdul:James', ['Abdul',"James","Stray"])
    (['Abdul', 'James', 'James'], 'James:Abdul:James')

    >>> get_sharing_info('Assets:Checking:James:Abdul:James:Foo:James:Abdul', ['Abdul',"James","Stray"])
    (['Abdul', 'James'], 'James:Abdul')

    >>> get_sharing_info('Assets:Checking:James:Abdul:James:Foo:James', ['Abdul',"James","Stray"])
    (['Abdul', 'James', 'James'], 'James:Abdul:James')

    >>> get_sharing_info('Assets:Checking:James:Foo:Abdul:James:Foo:Stray', ['Abdul',"James","Stray"])
    (['Abdul', 'James'], 'Abdul:James')
    """

    # Make regex for matching shared postings
    regex_s = "((" + "|".join(map(re.escape, members)) + ")(:\d+)?:?)"
    regex = re.compile(regex_s)

    # This is the part of the account name that does the sharing.  We
    # need to know it so we can replace it later.
    shared_notation = ""

    # List of members sharing this posting, with each included a
    # number of times equal to their share
    sharees = []  # type: list[str]

    last_end = 0
    matches = list(regex.finditer(account))
    for i in range(len(matches)):
        m = matches[i]

        # Start keeping track on the last set of contiguous matches
        # only
        if m.start() != last_end:
            if i == len(matches) - 1:
                continue  # don't match singletons at the end
            elif i < len(matches) - 1 and matches[i + 1].start() != m.end():
                continue  # don't match singletons
            else:
                shared_notation = ""
                sharees = []
        last_end = m.end()

        # Add to the shared account
        shared_notation += m.groups()[0]

        # What is the number after this member name? (Default to 1)
        if m.groups()[2]:
            multiple = int(m.groups()[2].split(":")[1])
        else:
            multiple = 1

        for i in range(multiple):
            sharees.append(m.groups()[1])

    # Remove trailing colon, if any
    if shared_notation.endswith(":"):
        shared_notation = shared_notation[:-1]

    if len(sharees) <= 1:
        return [], ""

    return (sorted(sharees), shared_notation)


def share_postings(
    entries: List[Any], options_map: Dict[str, Any], config: str
) -> Tuple[List[Union[data.Open, data.Transaction]], List[None]]:
    """Share postings among a number of participants (see module docstring for details).

    Args:
      entries: A list of directives. We're interested only in the Transaction instances.
      unused_options_map: A parser options dict.
      config: The plugin configuration string.

    Returns a tuple containing:

         * A list of entries, with potentially more accounts and potentially
           more postings with smaller amounts.

         * None

    """

    # Validate and sanitize configuration.
    if isinstance(config, str):
        members = config.split()
    elif isinstance(config, (tuple, list)):
        members = config
    else:
        raise RuntimeError(
            "Invalid plugin configuration: configuration for share_postings "
            "should be a string or a sequence."
        )

    # Filter the entries and transform transactions.
    open_entries = []
    new_entries = []
    for entry in entries:
        if isinstance(entry, data.Open):
            sharees, shared_notation = get_sharing_info(entry.account, members)
            if sharees:

                # Create Open directives for shared accounts if necessary.
                for member in sharees:
                    open_date = entry.date
                    meta = data.new_metadata("<share_postings>", 0)
                    open_entries.append(
                        data.Open(
                            meta,
                            open_date,
                            entry.account.replace(shared_notation, member),
                            None,
                            None,
                        )
                    )

                continue
        if isinstance(entry, data.Transaction):
            new_postings = []
            for posting in entry.postings:
                sharees, shared_notation = get_sharing_info(posting.account, members)
                if sharees == []:
                    new_postings.append(posting)
                    continue

                split_units = amount.Amount(
                    posting.units.number / len(sharees), posting.units.currency
                )

                for member in sharees:
                    subaccount = posting.account.replace(shared_notation, member)

                    # Ensure the modified postings are marked as
                    # automatically calculated, so that the resulting
                    # calculated amounts aren't used to affect inferred
                    # tolerances.
                    meta = posting.meta.copy()
                    meta[interpolate.AUTOMATIC_META] = True

                    # Add a new posting for each member, to an account
                    # with the name of this member.
                    if new_postings and subaccount == new_postings[-1].account:
                        ## Aggregate postings for the same member
                        new_amount = amount.Amount(
                            new_postings[-1].units.number + split_units.number,
                            posting.units.currency,
                        )
                        new_postings[-1] = posting._replace(
                            meta=meta,
                            account=subaccount,
                            units=new_amount,
                            cost=posting.cost,
                        )
                    else:
                        new_postings.append(
                            posting._replace(
                                meta=meta,
                                account=subaccount,
                                units=split_units,
                                cost=posting.cost,
                            )
                        )

            # Modify the entry in-place, replace its postings.
            entry = entry._replace(postings=new_postings)

        new_entries.append(entry)

    return open_entries + new_entries, []


if __name__ == "__main__":
    import doctest

    doctest.testmod()
