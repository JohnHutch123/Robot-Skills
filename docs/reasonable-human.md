# Reasonable Human profile: findings

Findings dated 2026-11-23. They are the basis for [`profiles/rs-rh.yaml`](../profiles/rs-rh.yaml) and the [Reasonable Human profile](../spec/rs-spec-v0.1.md#reasonable-human-profile) section of the spec.

## Short answer

No single machine-readable "typical human strength" profile exists, but the pieces do. Ergonomics standards publish design force limits for hands, arms and the whole body. Consumer studies publish how hard real people, including older people, can twist jar lids. Packaging standards then set how tight caps may be so that people can open them. RS combines these into one small profile that skills cite.

Products are designed to be opened by weak adults. So if a robot reaches a healthy adult's force and the object still has not moved, the likeliest cause is a wrong assumption, and the skill should branch rather than push harder.

## Sources

| Source | What it gives | Use in RS |
| --- | --- | --- |
| [EN 1005-3](https://cdn.standards.iteh.ai/samples/31655/634bfdeff8734b6b9a14f48568844ef6/SIST-EN-1005-3-2002-A1-2008.pdf) (machinery force limits) | Basic force capacities for grip, arm, whole-body push/pull and pedals. 15th percentile of adults aged 20 to 65 for professional use; 1st percentile for domestic use | Push, pull and grip values |
| [Yoxall and Rowson 2015, "Talking about torque"](https://eprints.whiterose.ac.uk/90469/1/Talking%20about%20Torque.pdf) | Review of nine lid-opening studies: peak torque by sex, age and lid size | Twist values |
| [ISO 17480](https://www.iso.org/standard/59881.html) (accessible packaging, ease of opening) | Requirements and test methods so packs open without tools | Supports "real products open within human limits" |
| ASTM D2063, ASTM D3474, ISO 16047 ([overview](https://www.mecmesin.com/test-type/removal-torque)) | How closure torque is measured; a vendor cites about 0.8 to 1.2 Nm for a 28 mm PET drink cap | Typical `expect` values |
| ISO 11228-1/-2/-3, NASA-STD-3001 Vol 2, MIL-STD-1472H, grip-strength norms | Lifting, pushing, carrying and grip data by percentile | Candidates for later versions; not yet checked |
| ISO/TS 15066 (collaborative robots) | Pain and injury thresholds for robot contact with people | Not strength data; a separate limit owned by the manufacturer |

## Lid-opening torque (from the review)

| Study | People | Lid | Men | Women |
| --- | --- | --- | --- | --- |
| Rohles et al. 1983 | 200, mean age about 73 | 67 mm | 6.50 Nm | 3.62 Nm |
| DTI 2000 | 144 | 65 mm smooth | 6.32 Nm | 4.51 Nm |
| Voorbij and Steenbekkers 2001 | 750, aged 20 to 80+ | 66 mm | 8.6 Nm | 5.6 Nm |
| Langley et al. 2005 | 235, aged 8 to 95 | 75 mm | 7.0 Nm | 4.8 Nm |
| Yoxall et al. 2010 | 317 | 75 mm | 5.8 Nm | 4.2 Nm |

The review gives a nominal jar opening torque of 2.9 to 5.5 Nm.

## Choices in version 1.0

- One adult profile (agreed 2026-11-25).
- `reasonable` targets the adult mean. For twisting it is 6.5 Nm on a 66 mm lid, near the adult male means above. For push, pull and grip only EN 1005-3 values were available, so `reasonable` uses its 15th-percentile professional column. That is lower than the mean, so a skill stops and branches earlier than intended.
- `weak` for twisting is the older women's mean from Rohles et al. 1983. For push, pull and grip it is the EN 1005-3 domestic (1st percentile) column.
- Twist values scale with lid diameter by d / 66 mm. This is an estimate: small caps are gripped with the fingertips, so real values may be lower.

## Gaps

- Pinch and fingertip values.
- Measured small-cap (20 to 40 mm) opening torque, to replace the scaling.
- Adult mean values for push, pull and grip.
- Whether older-adult or child-safe profiles are needed.
