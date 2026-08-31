# Proportional Multi-Line Phone Schedule Generator (Excel VBA)

Half-hourly requirement layer for **App_509** / **App_518**, 08:00–20:00 (24 slots), across Departments → Teams with Hamilton (largest remainder) apportionment and waterfall cap redistribution.

## Modules

| File | VBE type | Name |
|------|----------|------|
| `cTeam.cls` | Class Module | `cTeam` |
| `cDepartment.cls` | Class Module | `cDepartment` |
| `cPhoneScheduleOptimizer.cls` | Class Module | `cPhoneScheduleOptimizer` |
| `modMain.bas` | Standard Module | `modMain` |

## Import into Excel (Alt+F11)

1. Open a blank workbook (`.xlsm` — enable macros).
2. **File → Import File…** each of the four modules  
   **or** Insert Class/Module and paste the body (skip the `VERSION 1.0 CLASS` / `Attribute` header lines if pasting manually into a fresh class — when importing `.cls`/`.bas` as files, keep them).
3. For class modules created manually: set **(Name)** in Properties to match (`cTeam`, etc.).
4. No References required (late-bound `Scripting.Dictionary`).

### Manual paste tip

If Import fails on `.cls` headers, create an empty Class Module, rename it, then paste only from `Option Explicit` downward.

## Run

- `Run_Test_Case` — builds the mandatory sample, asserts A=9 / B=1 at 08:00 App_509, runs cap-hit edge (A=18,B=2), writes sheets.
- `Run_Production` — reads `Config_Teams` + `Config_Requirements` if present; otherwise runs the test case.

## Output sheets

1. **Requirement_Schedule** — Time | Line | Dept_ID | Team_ID | Required_FTE  
2. **Shift_Building_Helper** — 2-hour (4-slot) blocks + partials  
3. **Fairness_Report** — utilization, deviations, cap hits, shortfalls, jumps  

## Algorithm (summary)

1. Split interval requirement across departments by FTE weight (Hamilton + dept caps).  
2. Within each department, split to teams by weight with **waterfall**: floor → largest remainder → cap → redistribute until remainder=0 or all full.  
3. Log unmet demand as capacity shortfalls.
