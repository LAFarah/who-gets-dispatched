# Where this stands

Column names, technology categories, products and dispatch types are now verified
against the live UKPN schema. `docs/schema.txt` is the record of that.

## Run it

```powershell
$env:PYTHONPATH="src"
$env:UKPN_API_KEY="your-new-key"
python -m pytest -q          # 37 tests, no network needed
python -m ukpn.pipeline      # full extract, validate, analyse, figures
streamlit run app.py
```

## Open questions the full extract will settle

1. **Is `dispatch_method` ever anything but `epex`?** All 2,000 sampled rows say
   `epex`, but the field is documented as "API or email". If email never appears, the
   field is vestigial and worth asking about. If it appears only in older data, that
   is a migration story.

2. **Do `demand_turn_up` and `generation_turn_down` appear before April 2026?** They
   shouldn't — bi-directional flexibility went live then. Anything earlier is either a
   trial or a data issue.

3. **Does `fu_id` ever equal `zone`?** The sampled row showed `Cobham` for both, which
   breaks the pattern of every other unit identifier (`OCTO-WILL-LTU-F8CF`). Could be a
   naming convention for single-unit zones, could be a placeholder. There is a check
   for it.

4. **Do the legacy products (Sustain, Secure, Dynamic) still appear?** The field
   description mentions Dynamic, but only the four current products appeared in the
   sample. If legacy rows exist earlier in the history, the product transition is
   itself a finding.

5. **Does availability ever carry a non-zero price for domestic DSR?** The sample row
   is utilisation-only. If domestic providers systematically forgo availability
   payments, that is a real commercial asymmetry against grid-scale.

## Before publishing

- Sense-check any exception rows by hand. If the count is non-trivial, email the UKPN
  open data team asking whether you have misread a field. Starting that relationship
  is worth more than the repo.
- Tone: "I reproduced UKPN's published checks to understand the data and found N rows
  worth asking about." Never "UKPN's data is wrong."
- Decide what goes public. See the note on provider-level analysis below.

## On the provider-level cut

The dataset names companies. That makes competitor comparison trivial, and it is the
most commercially interesting thing here — but it is also the part that needs
judgement about what is published versus what is discussed privately.
