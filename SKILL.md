---
name: gendesign
description: AI + generative design for a physical part. Requirements, then analysis, then generate and search, then an AI review, the owner's go, a test, and feedback. Use when designing, iterating, or reviewing a part under models/. Nothing here starts a print.
---

# gendesign

You are the AI in "AI + generative design". The code generates and scores; you decide what each round should test, read the renders, say what the scores miss, and propose the next step. The owner decides what gets printed.

## Order of work

1. **Requirements.** `models/<name>/requirements.yaml`, measured, with units. Never invent a fit-critical number. If a needed number is missing, use a stated reference and list it as an open question.
2. **Analysis before geometry.** `gendesign analyze models/<name>`. `analyze()` in `model.py` turns requirements into targets (each with the requirement it came from and the equation), says which requirement binds and which has margin, and screens concepts. The chosen concept picks the generator. Do not start by drawing a shape and scoring it.
3. **Round.** `gendesign round models/<name> [--from iterations/NN] --note "<what changed and why, who decided>"`. Keep rounds short. A round refuses to run without `analysis.json`.
4. **Review.** Open `picks.png` and each `picks/<pick>/preview.png`. In `decisions.md`, fill *AI review* and *Proposed next*: compare against the targets, name what the renders show that the scores miss, and do not claim more than the evaluators know.
5. **Report.** `gendesign report models/<name>` after each review, so `REPORT.md` is current for the owner.
6. **Owner go.** Only the owner runs `gendesign approve`. Never run it yourself, never send a file to a printer.
7. **Print files.** `gendesign generate models/<name> <pick>`. The mesh check must say watertight, one body, nothing over air.
8. **Feedback.** After a print, a `test.md` next to the pick: printed?, settings, measured vs designed, fit/function, photos, failure notes, next change. Put corrections as lines `gendesign feedback` can read:

   ```
   - calibrate: drainage.cd = 0.55 (predicted 0.61) timed 100 ml through the grate
   - requirement: fit.flange_diameter_mm — calipered 44.8, the 46 was assumed
   ```

   A calibration corrects an evaluator in the next analysis and round. A requirement flag goes to the owner; only the owner edits `requirements.yaml`.

## Rules for the scores

- A shape preference is not an objective. If a round hole is better, a functional score (stress, snag, corner water) has to say so. If none does, say the model is missing that score.
- Constraints come from the analysis targets. Objectives are what is left to trade.
- Every evaluator lists its uncertainties; repeat them in the review.

## Print rules

Flat face on the bed. No supports unless the model says so. No flat ledge over air (45° cones or chamfers). 100% infill on small parts.

## Where things are

`gendesign/loop.py` is the loop. `gendesign/process.py` has `Generator` and `Evaluator`. `gendesign/field.py` builds and meshes signed-distance parts. Each `models/<name>/` has `model.py`, `analysis.md`, `REPORT.md`, `designs/`. Old scripts are under `models/<name>/archive/`; they are records, not a second framework.
