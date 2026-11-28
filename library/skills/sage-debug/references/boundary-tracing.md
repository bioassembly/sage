# Trace failures across boundaries

1. Identify the failing operation and the input or state that violated its contract. Trace that value back across its callers until you find where it first diverges from the expected value.
2. At uncertain boundaries, correlate one failing run with a healthy run. Record the operation ID, attempt, state transition, and sanitized input shape at both ends. In concurrent work, capture the order of events instead of inferring it from console output alone.
3. For suspected test pollution, run the failing test alone in clean state, then replay its original predecessors. Reset state on each attempt. Narrow the prefix only if the failure reproduces reliably from that prefix. Check the suspected predecessor and failing test together.
4. For races, wait for the underlying readiness condition with an explicit deadline. On timeout, report the last observed state. Use a known synchronization point to exercise the failing order in a regression test.
5. Fix the earliest owned boundary that creates the invalid state. Keep contract checks that prevent downstream damage. Verify one failing case and one normal case through the caller that depends on the contract.

Adapted from [Superpowers systematic debugging](https://github.com/obra/superpowers/tree/22f0b463e7a5e579904dd6211a520321035526f7/skills/systematic-debugging).
