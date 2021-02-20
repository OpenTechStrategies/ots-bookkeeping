# OTS Bookkeeping Tools

We use [Beancount](https://github.com/beancount/beancount) for
bookkeeping and light accounting.  This repository holds various tools
to help with that.

# Setup

Set the `OTS_BOOKKEEPING_DIR` environment variable to the absolute path of
the directory containing this code.  Our convention is that programs
using this code will locate it by examining that environment variable.

# What's here

## ots-bean-check

A script that runs OTS-specific checks on a Beancount file (for
example, checking that the entries are in chronological order).

## share_postings.py

`share_postings.py` is a beancount plugin that enables you to
automatically split a posting among multiple parties.

## threadfin

threadfin is a set of tools that make beancount easier.  It consists
of several subtools, all of which can be accessed via `threadfin
TOOLNAME`.  See `threadfin/README.mdwn` for more information.

## ots-generate-1099, fill-1099

`fill-1099` is a script for arranging payment information properly on
a standard U.S. 1099-MISC PDF form.  The script knows the layout: you
pass in the payee and payment data and it takes care of the rest.

`ots-generate-1099` is an OTS-specific driver for `fill-1099`.
Usually you would expect to be running `ots-generate-1099`, rather
than running `fill-1099` directly.
