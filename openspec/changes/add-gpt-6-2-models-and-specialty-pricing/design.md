## Decisions

- Bootstrap metadata mirrors the live Codex catalog captured 2026-11-17, not the public API page; a successful registry refresh stays authoritative.
- GPT-6.2 plan set is the GPT-6 set minus `free`, `free_workspace`, `k12`, plus `hc_consumption`, `law`, `rosalind_academic`.
- Ultrafast is modelled as `ultrafast_multiplier` over Standard short/long rates because every published Ultrafast row is an exact multiple (GPT-6.2: 3x, GPT-6.1 Sol: 6x). Models without a multiplier keep the existing behaviour (Fast rates).
- GPT-6.2 has no published Flex tier, so no Flex rates are set and Flex requests price at Standard.
- Specialty rows copy the upstream pricing snapshot (`origin/chore/upstream-metadata`, 2026-11-15).

## Risks

- GPT-6.2 Ultrafast becomes 6x Standard on 2027-03-01; the multiplier must be updated then.
- Bootstrap entries go stale; they only matter before the first registry refresh.
