"""Rules package — universal, stateless editorial functions.

Each rule is a pure function: string in, string out, no side effects, no global
state. Rules do not call each other; the per-novel pipeline orchestrates order.
These are reusable across every novel profile (see build spec: Universal vs.
Novel-Specific Rules).
"""
