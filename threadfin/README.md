# Threadfin

Threadfin is a set of utilities for working with ledger files.  Look
at the appropriate README.md for each utility.  Run the
utility with `threadfin foo bar baz` where "foo" is the name of the
utility and "bar" and "baz" are options to that utility.  You'll
probably want to place `bin/threadfin` somewhere on your path.

For example: `threadfin sort /path/to/ledger/file`.

# threadfin.yaml / config.yaml

Each statement dir can have a `threadfin.yaml` in which config can
live.  The format and use of `threadfin.yaml` files isn't fully baked,
so we haven't documented it yet.  Indeed, even the name isn't fully
baked: some parts of this code base call it `config.yaml` or something
similar.  This should all be made consistent eventually.

# Convert
Converts statements to beancount files.  Point it at a directory of
statements or csv files, and convert will generate corresponding
beancount files.  Try something like this to see how it works:

    threadfin convert ~/OTS/finances/statements

or
    threadfin convert examples/aadvantage

That first command is useful because you end up with a bunch of
beancount files representing your statements, and those are very
useful for finding matching entries that are simply dated wrong in
your main file.  You can also copy+modify entries into your actual
beancount file from there.

`convert` can parse a few different types of bank and credit card
statements PDFs, including Chase, Bank of America, TDBank, and Capital
One credit cards.  It can also handle CSV files from American
Aadvantage cards.  See the invididual converters in the `convert`
directory to examples on how to write your own converter.  CSV
converters are the easiest to write and maintain.

One useful feature in the conversion is that we can put info in
threadfin.yaml that allows us to tag and comment matching entries.
For example, this allows us to generate a beancount version of a
credit card statement with the business expenses tagged.  You have the
overhead of having to write auto-tag entries, but you can write them
to match multiple entries so that they capture recurring payments.

## Inbox

Parse those invoices in your inbox for transaction data.  This
directory contains scripts that can each parse a different service.

We recommend making a separate beancount file for each service you
want to automatically work with.  Here's an example using
`digital-ocean`:

    inbox digital-ocean -w /path/to/statements /path/to/digital_ocean.beancount

See `inbox/digital-ocean` for more detail.

# Open-Close

Generate open and close directives based on a beancount file or a
directory of beancount files.

    threadfin open-close path/to/beancount/files

# Reconcile
Reconcile two beancount files.  This is useful for a bank account when
you want to make sure the hand-coded entries match the bank
statements.

# Sort
Sort a beancount file's entries by date.
