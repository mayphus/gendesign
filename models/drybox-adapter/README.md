# Drybox adapter

Worked example for [gendesign](../../README.md): a small grommet that holds a PTFE bowden insert in a filament-dryer wall. It has a flared mouth, a pocket, a 45° cone floor and a barbed stem.

**Review it here: [REPORT.md](REPORT.md).** Targets and concept: [analysis.md](analysis.md).

The analysis says fit, not strength, decides this part. The pocket target is the calipered 8.7 mm pin plus the 0.1–0.2 mm that printed holes come out small: 8.85 mm, with coupons at 8.80–8.90. Topology optimization was screened out because nothing here carries load worth optimizing. The generator is a one-gene pocket sweep, and the real test is a printed coupon.

```bash
gendesign analyze models/drybox-adapter
gendesign round models/drybox-adapter --pop 6 --gens 2
gendesign report models/drybox-adapter
python models/drybox-adapter/generate.py -P 8.85      # one part directly (CadQuery)
```

After printing coupons, write the measured undersize into the coupon's `test.md` as `- calibrate: fit.undersize_mm = 0.18`, run `gendesign feedback` on it, then `gendesign analyze` again. Do not start a print until the owner says go.
