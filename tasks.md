## List of tasks to accomplish in order

- [x] Task 1 : In view_segment, panning on the graphs (elevation, power, etc) doesn't correlate with a red dot moving around on the map, unlike in new_segment. Please align both versions, so the red dot is always present.
- [x] Task 2 : In both view_segment and new_segment, endpoints are denoted by a google maps location icon. Replace these with a green round dot for start, and a checkered dot for finish.
- [x] Task 3 : In view_segment, put the title of the segment on the right. Add the option to edit title and comments, in addition to the current edit parameters option
- [x] Task 4 : In new_segment, all three charts display data when one hovers on them, and display the location dot on the map. However, only the top chart is "selectable", is the user can brush to select a subsegment. Make this possible for all displayed charts.
- [x] Task 5 : In new_segment, the peucker_douglas is limited to 5 segments. Hwever, when a segment is seen in view_segment, the peucker douglas shown contains more segments. Unify both these elements such that all display the same amount of segments : to do so, add a cutoff for the elevation diff of a newly created segment (same as with the current new_segment, but without a 5 segment limit.)
- [x] Task 6 : The small red marker on the map moves way smoother in view_segment compared to new_segment. This can be caused either by just data management, or by just various approaches. Please do your best to diagnose and fix
- [x] Task 7 : in view_segments, the comment field now appears twice (on top, and below the parameters). Remove it from the parameters box.



