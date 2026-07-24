# hatty — MIT License. See LICENSE file for details.
"""Controllers own slices of HACLI's state and mutations (lists, dashboards,
graphs). Each takes the app in its constructor for notify/persist/screen
access; HACLI exposes their state through property pairs so the app's public
surface (used by screens and tests) is unchanged."""
