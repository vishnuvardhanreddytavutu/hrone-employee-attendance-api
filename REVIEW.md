REVIEW.md

Defects Found in the Starter Code

| # | Where (function / line) | What is wrong | How you'd notice it (test, input, or symptom) | How you fixed it |
|---|---|---|---|---|
| 1 | Department trend endpoint — `$densify` stage | The upper bound excluded the final requested date because the upper boundary was midnight at the start of that date. | Request a trend from `2026-10-01` to `2026-10-13` and check whether October 13 appears in the results. | Set the exclusive upper bound to midnight on the day after the requested end date. |
| 2 | Department trend endpoint — `$setWindowFields` stage | The rolling-window sort used the string-valued `date` field instead of a BSON Date field, which MongoDB requires for this date-range window. | Request a department trend and observe the MongoDB error about the sort field needing to be a Date. | Sort the window by the BSON Date field, `day`. |
| 3 | Department trend endpoint — working-day calculation | The day-of-week condition incorrectly included Sunday and excluded Saturday. | Test dates falling on Saturday and Sunday and inspect the `is_working_day` value. | Use MongoDB day-of-week values 2 through 6 for Monday through Friday. |
| 4 | `validate_date()` helper | `date.fromisoformat()` accepted compact dates and ISO week dates instead of enforcing `YYYY-MM-DD`. | Test `20261013` and `2026-W42-2`; both were accepted before the fix. | Added a strict `YYYY-MM-DD` regular-expression check before parsing the date. |

| 5 | `/attendance/punch-in` — attendance date assignment | Overnight-shift punches before the shift end were assigned to the current IST date instead of the previous shift-start date. | Test a 02:00 IST punch for a 22:00–06:00 shift. | Assign early-morning punches to the previous date when the shift is overnight and the punch time is before shift end. |


Items Checked and Not Considered Defects

| Item checked | Why it was not considered a defect |
|---|---|
| Late-minute grace boundary | Tests confirmed that a delay of exactly 10 minutes is not late, while a delay of 10 minutes and 1 second produces 10 late minutes. |
| Half-up rounding helper | Tests confirmed that values such as `4.445` round to `4.45` and `7.125` round to `7.13`. |
| Work-hours calculation | A 09:30 to 14:00 interval correctly produces 4.50 work hours. |

**Note:** These are the defects and checks verified so far. The review is not complete until the remaining helpers and endpoints in the starter `app/main.py` have been inspected against the assignment requirements.
