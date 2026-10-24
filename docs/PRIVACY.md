# Privacy

The public text is the **Privacy notice** in the app (`#/privacy`, source `frontend/src/pages/Legal.tsx`). What is
stored and for how long is in `DATA_RETENTION.md`. How each statement was checked against the code is in
`legal-audit.md`. None of this is legal advice; items that need a lawyer or the operator's confirmation are listed
there.

Rule for changes: when behaviour changes (a new cookie or browser storage key, a new provider, a new retention
period, a new counted page), change the code, the notice, `DATA_RETENTION.md` and the test in
`frontend/src/test/legal.test.tsx` together.
