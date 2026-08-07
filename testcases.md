Since this is an enterprise safety platform, your testing should cover **all branches of your pipeline**, not just happy paths. A good test suite should validate:

* Information extraction
* Agent routing
* RAG lookups
* PubChem integration
* MCP hardware validation
* Supervisor decision logic
* SDS generation trigger
* Error handling

Below are **20 realistic test cases** with their expected outputs.

---

# Test 1 — Safe Water Mixture

### Input

```
Mix 90% Water and 10% Ethanol.
Store in borosilicate glass.
Heat to 40°C.
```

Expected Extraction

```
Chemicals:
- Water 90%
- Ethanol 10%

Hardware:
- Borosilicate Glass

Temperature:
40°C

Generate SDS:
No
```

Expected Agent Results

Chemical Compliance

```
No OSHA concern.
Low concentration.
```

PubChem

```
Ethanol
Boiling Point: 78°C
```

Hardware

```
40°C within safe limit.
PASS
```

Final Verdict

```
APPROVED
```

---

# Test 2 — Acetone Above Boiling Point

Input

```
Mix 80% Water
20% Acetone

Heat to 70°C
Use Borosilicate Glass
```

Expected

```
Acetone BP = 56°C

70°C > 56°C

Hardware PASS

Boiling Point FAIL

Verdict:
REJECTED
```

---

# Test 3 — Toluene Safe Heating

Input

```
40% Toluene
60% Water

Heat to 90°C

Container:
Stainless Steel
```

Expected

```
Boiling Point:
111°C

90°C <111°C

Hardware PASS

Verdict

APPROVED
```

---

# Test 4 — Methanol Dangerous

Input

```
100% Methanol

Heat to 90°C

Container:
Stainless Steel
```

Expected

```
Boiling Point
65°C

Heating exceeds boiling point

Verdict

REJECTED
```

---

# Test 5 — Hardware Failure

Input

```
50% Water
50% Ethanol

Heat to 250°C

Container
Polypropylene
```

Expected

```
Hardware Agent

Temperature exceeds Polypropylene limit

FAIL

Chemical

Ethanol BP
78°C

Supervisor

REJECTED
```

---

# Test 6 — Multiple Solvents

Input

```
30% Acetone

30% Methanol

40% Water

Heat to 50°C

Container
Glass
```

Expected

```
Acetone BP
56°C

Methanol
65°C

50°C below both

Verdict

APPROVED
```

---

# Test 7 — Multiple Failures

Input

```
50% Acetone

50% Methanol

Heat to 100°C

Container
Polypropylene
```

Expected

```
Acetone FAIL

Methanol FAIL

Hardware FAIL

Final

REJECTED
```

---

# Test 8 — Unknown Chemical

Input

```
40% DragonBloodExtract

60% Water

Heat to 40°C
```

Expected

```
PubChem

Chemical not found

Supervisor

REVIEW_REQUIRED
```

---

# Test 9 — Unknown Hardware

Input

```
70% Water

30% Ethanol

Container
Alien Alloy Reactor
```

Expected

```
Hardware Unknown

Supervisor

REVIEW_REQUIRED
```

---

# Test 10 — Missing Temperature

Input

```
80% Water

20% Ethanol

Container
Glass
```

Expected

```
Temperature Missing

Supervisor

REVIEW_REQUIRED
```

---

# Test 11 — Missing Container

Input

```
80% Water

20% Acetone

Heat to 40°C
```

Expected

```
Hardware Missing

Supervisor

REVIEW_REQUIRED
```

---

# Test 12 — SDS Generation

Input

```
60% Water

40% Toluene

Heat to 30°C

Generate SDS
```

Expected

```
Pipeline executes

Safety PASS

16-section SDS generated
```

---

# Test 13 — No SDS Request

Input

```
60% Water

40% Toluene

Heat to 30°C
```

Expected

```
Pipeline executes

No SDS generated
```

---

# Test 14 — Natural Language Parsing

Input

```
Take some acetone around twenty percent and mix it with eighty percent water.
Warm it to seventy degrees inside a borosilicate flask.
```

Expected

```
Extraction

Water
80%

Acetone
20%

Temperature
70°C

Container
Borosilicate

Boiling Point FAIL

Verdict

REJECTED
```

---

# Test 15 — Decimal Values

Input

```
Water 94.5%

Acetone 5.5%

Heat 35.7°C

Container Stainless Steel
```

Expected

```
Decimals parsed correctly

APPROVED
```

---

# Test 16 — Lowercase Input

Input

```
mix 50 acetone and 50 water
heat to 45
use stainless steel
```

Expected

```
Extraction succeeds

APPROVED
```

---

# Test 17 — Mixed Order

Input

```
Heat to 45°C.

Container Stainless Steel.

Mix 20% Ethanol

80% Water.
```

Expected

```
Parser independent of order

APPROVED
```

---

# Test 18 — Large Formulation

Input

```
25% Water

20% Ethanol

15% Methanol

10% Acetone

15% Benzene

15% Toluene

Heat to 60°C

Container Stainless Steel
```

Expected

```
Acetone FAIL

56°C exceeded

Others checked

Supervisor

REJECTED
```

---

# Test 19 — PubChem API Failure

Mock Condition

```
PubChem unavailable
```

Expected

```
PubChem Agent

Timeout

Supervisor

REVIEW_REQUIRED
```

---

# Test 20 — Complete Happy Path with SDS

Input

```
Prepare a formulation:

70% Water

20% Isopropanol

10% Ethanol

Store inside Borosilicate Glass.

Heat to 50°C.

Generate SDS.
```

Expected

```
Extraction SUCCESS

Chemical Agent PASS

PubChem PASS

Hardware PASS

Supervisor

APPROVED

Generate complete 16-section SDS
```

---

## Additional Edge Cases Worth Testing

| Scenario                                                | Expected Result                                          |
| ------------------------------------------------------- | -------------------------------------------------------- |
| Percentages don't sum to 100%                           | REVIEW_REQUIRED or validation warning                    |
| Duplicate chemical listed twice                         | Merge or warn depending on implementation                |
| Negative temperature (-20°C)                            | Usually APPROVED if hardware supports it                 |
| Temperature written as "seventy degrees"                | Correctly parsed to 70°C                                 |
| "Heat until boiling"                                    | REVIEW_REQUIRED unless resolved to a numeric temperature |
| Empty input                                             | Validation error                                         |
| Only "Generate SDS" with no formulation                 | Validation error; no SDS                                 |
| Extra punctuation and typos                             | Robust parsing where possible                            |
| Unsupported concentration units (e.g., "10 mL acetone") | REVIEW_REQUIRED or unit conversion if supported          |
| More than 20 chemicals in one formulation               | Pipeline remains stable; supervisor evaluates all        |



That's even better. If your pipeline supports **jurisdiction selection** (OSHA, EU CLP, WHMIS, etc.) and **language localization**, you should test those independently as well as in combination with the chemistry workflow.

---

# Jurisdiction Test Cases

## Test J1 — Default Jurisdiction (OSHA)

### Input

```text
Jurisdiction: OSHA

Mix 80% Water and 20% Acetone.

Heat to 40°C.

Container: Borosilicate Glass.
```

Expected

```text
Jurisdiction Selected:
OSHA

Compliance Agent:
Loads OSHA vector database

Verdict:
APPROVED
```

---

## Test J2 — European CLP

Input

```text
Jurisdiction: EU CLP

40% Ethanol
60% Water

Heat to 40°C

Container Stainless Steel
```

Expected

```text
Compliance Agent

Loads EU CLP regulations

Uses EU hazard classifications

Verdict
APPROVED
```

---

## Test J3 — WHMIS (Canada)

Input

```text
Jurisdiction: WHMIS

50% Methanol

50% Water

Heat to 80°C
```

Expected

```text
Compliance Agent

Loads Canadian WHMIS regulations

Methanol BP exceeded

Verdict

REJECTED
```

---

## Test J4 — Unsupported Jurisdiction

Input

```text
Jurisdiction: Mars Chemical Authority

20% Acetone

80% Water
```

Expected

```text
Compliance Agent

Jurisdiction not supported

Supervisor

REVIEW_REQUIRED
```

---

## Test J5 — Missing Jurisdiction

Input

```text
30% Toluene

70% Water

Heat to 40°C
```

Expected

```text
Default jurisdiction selected

(OSHA if configured)

Pipeline continues
```

---

# Language Support Tests

## Test L1 — English

Input

```text
Language: English

Mix 80% Water

20% Acetone

Generate SDS
```

Expected

```text
Entire response

English

SDS

English
```

---

## Test L2 — Spanish

Input

```text
Language: Spanish

Mix 70% Water

30% Ethanol

Generate SDS
```

Expected

```text
SDS generated entirely in Spanish

Warnings

Spanish

Section titles

Spanish
```

---

## Test L3 — German

Input

```text
Language: German

40% Methanol

60% Water

Generate SDS
```

Expected

```text
German localized SDS

German GHS wording

German section headings
```

---

## Test L4 — French

Input

```text
Language: French

20% Acetone

80% Water
```

Expected

```text
French response

French hazard statements
```

---

## Test L5 — Hindi

Input

```text
Language: Hindi

40% Water

60% Ethanol
```

Expected

```text
Pipeline runs normally

Output localized

Hindi language
```

---

## Test L6 — Unsupported Language

Input

```text
Language: Klingon

20% Water

80% Acetone
```

Expected

```text
Language unsupported

Fallback to English

or

Prompt user to select a supported language
```

---

# Combined Pipeline Tests

## Test C1 — OSHA + English

```text
Jurisdiction: OSHA

Language: English

80% Water

20% Acetone

Heat to 70°C

Container Borosilicate

Generate SDS
```

Expected

```text
OSHA rules loaded

English SDS

Acetone BP exceeded

REJECTED
```

---

## Test C2 — EU CLP + German

```text
Jurisdiction: EU CLP

Language: German

70% Water

30% Ethanol

Heat to 40°C

Generate SDS
```

Expected

```text
EU regulations

German SDS

APPROVED
```

---

## Test C3 — WHMIS + French

```text
Jurisdiction: WHMIS

Language: French

100% Methanol

Heat to 90°C

Generate SDS
```

Expected

```text
Canadian compliance

French SDS

REJECTED
```

---

## Test C4 — Unknown Jurisdiction + Spanish

```text
Jurisdiction: XYZ

Language: Spanish

80% Water

20% Acetone
```

Expected

```text
Jurisdiction error

Spanish error message

REVIEW_REQUIRED
```

---

## Test C5 — Hardware Failure + German SDS

```text
Jurisdiction: OSHA

Language: German

40% Water

60% Ethanol

Heat to 250°C

Container Polypropylene

Generate SDS
```

Expected

```text
Hardware Agent FAIL

Supervisor

REJECTED

German SDS still generated (if your design generates SDS even for rejected formulations)
```

---

# Stress Tests

### Test S1 — Random Capitalization

```text
jUrIsDiCtIoN: oShA

lAnGuAgE: EnGlIsH

70% WATER

30% AcEtOnE
```

Expected

```text
Case insensitive parsing

Pipeline succeeds
```

---

### Test S2 — Language First

```text
Spanish

OSHA

Mix

20% Acetone

80% Water
```

Expected

```text
Correct language detection

Correct jurisdiction

Pipeline succeeds
```

---

### Test S3 — Natural Language

```text
Please follow OSHA regulations.

Respond in German.

Mix 20 percent acetone with 80 percent water.

Heat it to 40 degrees.

Generate an SDS.
```

Expected

```text
Jurisdiction extracted

Language extracted

German SDS generated

APPROVED
```

---

### Test S4 — Missing Language

```text
Jurisdiction OSHA

80% Water

20% Ethanol
```

Expected

```text
Default language

English
```

---

### Test S5 — Missing Both

```text
20% Ethanol

80% Water

Heat to 40°C
```

Expected

```text
Default Jurisdiction:
OSHA

Default Language:
English

Pipeline continues
```

---

## Coverage Summary

| Feature                          | Test IDs |
| -------------------------------- | -------- |
| Default jurisdiction             | J1, J5   |
| Multiple jurisdictions           | J2, J3   |
| Invalid jurisdiction             | J4, C4   |
| English localization             | L1       |
| Spanish localization             | L2       |
| German localization              | L3       |
| French localization              | L4       |
| Hindi localization               | L5       |
| Unsupported language             | L6       |
| Combined jurisdiction + language | C1–C5    |
| Natural language extraction      | S2, S3   |
| Case-insensitive parsing         | S1       |
| Default fallback behavior        | S4, S5   |

