What's here:

* `main.beancount`: Sample data in Beancount, showing a bunch of
  transactions.

* `ccsample.beancount`: A credit card statement that has been
   converted to Beancount format.  This is intended to be reconciled
   with `main.beancount`.

* `example_config.yaml`: An example config file that you could use for
   that reconciliation run.

Try running

```
  $ cd ../..   # get to the top of the ots-bookeeping tree

  $ cp threadfin/examples/generic_samples/example_config.yaml ./my-config.yaml

  $ ${EDITOR} my-config.yaml   # edit as needed

  $ ./threadfin/bin/threadfin reconcile --config my-config.yaml main chase
```

See ../../reconcile/README.md for more about reconciliation.
