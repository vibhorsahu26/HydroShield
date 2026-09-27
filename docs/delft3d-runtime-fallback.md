# Delft3D Runtime Fallback

A normal simulation request does not require Delft3D FM to be installed in a development deployment.

- If a native Delft3D runtime is detected, the normal job path uses it.
- If it is not detected, the normal job path uses HydroShield's internal calculation engine and continues through the same results, analysis, comparison, and export pipeline.
- An explicit native execution request remains strict and fails early when Delft3D FM is unavailable.

The UI does not expose execution mode.
