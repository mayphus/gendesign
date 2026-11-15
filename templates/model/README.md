# (Model name)

Worked example for [gendesign](../../README.md). One paragraph: what the part is and what it must do.

Review state: [REPORT.md](REPORT.md). Targets and concept: [analysis.md](analysis.md).

```bash
gendesign analyze models/<name>      # requirements -> targets -> concept
gendesign round   models/<name>      # generate + search; writes designs/<design>/iterations/NN
gendesign report  models/<name>      # REPORT.md for review
gendesign generate models/<name> designs/<design>/iterations/NN/picks/knee   # print files
```

After a print the owner asked for, add `test.md` next to the pick and run `gendesign feedback` on it.
