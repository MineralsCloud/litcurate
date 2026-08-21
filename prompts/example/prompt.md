Extract STATIC equation-of-state (EOS) parameters for lower-mantle-relevant phases
into the flat schema. Priority fields: **V0, K0, and Kp (K′)**. Values and units
must be copied exactly as reported.

Target phases (keep these; skip unrelated crustal/transition-zone-only phases unless
explicitly framed as lower-mantle):
- bridgmanite / (Mg,Fe)SiO3 or MgSiO3 perovskite (Pv)
- ferropericlase / magnesiowüstite / periclase / (Mg,Fe)O / MgO
- post-perovskite (PPv)
- CaSiO3 perovskite (CaPv)
- closely related deep-mantle SiO2 or hydrous phases only when discussed with EOS numbers

For each distinct phase + composition + sample/table row + EOS model, return one entry.

Promote when present:
- `V0` (+ `V0_unit`, `V0_name`, `V0_basis`, `V0_determination`)
- `K0` (+ `K0_unit`, `K0_name`, `K0_type`, `K0_determination`)
- `Kp` for K′ / K0′ / K_T′ (+ `Kp_name`, `Kp_determination`)

Determination enums:
- `V0_determination`: `measured` | `fitted` | `assumed` | `unknown`
- `K0_determination`: `fitted` | `measured` | `assumed` | `unknown`
- `Kp_determination`: `fitted` | `fixed` | `assumed` | `unknown`

Ambient / Table zero-pressure unit-cell volumes used with an EOS fit → fill `V0`
with `V0_determination: measured` even if the text only quotes fitted K0 and fixed
K′. Do not park those volumes only in `extra_info`.

Also set: `eos_model`, `method`, `T_ref`/`P_ref` (+ units), `origin`
(`this_study` | `cited` | `unknown`).

INCLUDE literature-tabulated V0/K0/K′ when reported numerically (`origin: cited`).
Other parameters (γ0, θ0, q, α, …) → `extra_info` only.
`evidence` is one string. Do not invent values or convert units.
If no relevant static EOS parameters appear, return `{ "eos_entries": [] }`.

Return JSON matching the schema: `{ "eos_entries": [ ... ] }`.
