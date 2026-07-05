# Progress — tasks.md items 8, 9, 10 (2026-07-05)

UI pass on the activities (history) and routes tables. Baseline: 33/33 tests pass.

## Task 10 — routes default to "New Route"
GPX upload stored the filename as the title. Change it to `'New Route'` (mirrors the FIT flow's
`'New Activity'`), and make the routes-table fallback for a missing title show "New Route" too.

## Task 8 — sleeker delete pop-ups, no bin image
Redesign the delete (and rename) modals in history.html + routes.html into one clean system:
rounded card, dimmed+blurred single shared overlay, title + subtitle + a pill "Cancel"/"Delete"
pair. Drop the `bin.png` image (only the activity-delete modal used it). Fitness-app aesthetic:
soft shadows, rounded pills, subtle pop-in.

## Task 9 — multi-select + bulk delete
Add a "Select" toggle (top-right of each table's filter bar). In select mode a checkbox column
appears on the right of the table and a bulk-action bar shows "N selected" + "Delete selected".
Confirming opens the sleek modal, then a JS-built POST submits the checked ids to new endpoints:
- `/delete_files` (activities): delete each owned activity + its segments + FIT file.
- `/delete_routes` (routes): delete each owned route + its GPX file.
Both reuse the existing ownership checks; ids the user doesn't own are skipped. Row-click navigates
normally but toggles the checkbox while in select mode. URL map gains 2 routes → regenerate fixture.

## Verification — DONE
- New tests (3): bulk delete of activities removes only owned rows + cascades segments and ignores
  another user's id; same for routes; GPX upload titles the route "New Route". Suite: 36/36 pass.
  urlmap fixture regenerated (+/delete_files, +/delete_routes).
- Browser E2E (11/11 checks, no page errors): 3 activities uploaded; delete modal is the new sleek
  card with Cancel/Delete pills and NO bin image / no <img>; Select mode reveals the right-hand
  checkbox column + bulk bar counting "2 selected"; bulk-delete confirm modal shows the count;
  2 deleted / 1 remains; routes list shows "New Route"; route bulk-delete empties the list.
  Screenshots reviewed — clean fitness-app aesthetic.
