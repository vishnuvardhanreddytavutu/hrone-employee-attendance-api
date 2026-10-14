DECISIONS.md

1. Indexes
I created eight indexes. The unique employee-code index prevents duplicate employees. The unique employee-code and date index prevents duplicate attendance records. Other indexes support department lookups, employee joining dates, attendance date and status filters, and late-minute leaderboard queries. I would consider a compound index for a specific analytics query only after checking its execution plan.

2. Punch-in race
If two identical punch-in requests arrive together, both may check that the employee exists. Both then try to insert an attendance record. The unique index on employee code and date allows only one insert. The other raises a duplicate-key error, which the API returns as HTTP 409 Conflict.

3. Ties
The leaderboard uses MongoDB's `$rank` to assign equal ranks to employees with the same total late minutes. It filters by rank rather than limiting the number of rows, so if several employees tie at the cutoff rank, all of them are returned. The final sort by employee code makes the output order predictable.

4. Headcount
The department summary starts with employees who joined by the end of the selected month and joins attendance records. Employees without logs can therefore still contribute to headcount.

 5. Scaling
For 100 times more data, I would inspect real query execution plans, test with a larger dataset, and adjust indexes based on measured performance.