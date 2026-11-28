# Deepen a module

Find a cluster of callers that know the same sequence, validation rules, or recovery steps. Pick a concrete operation and list what each caller must know to perform it today. Sketch two interfaces that put those decisions in the module while preserving the caller's intent.

| Dependency | Practical seam |
| --- | --- |
| In-process computation and state | Test the behavior through the module's public operation. |
| Storage with a faithful local substitute | Exercise the relevant constraints and failure cases using the substitute inside the integration test. |
| A service the team owns | Introduce an adapter when transport details would otherwise leak into callers. Test the module contract and the production transport independently. |
| A third-party service | Keep its request shape, response mapping, and retry rules at the boundary. Use recorded or synthetic responses to test expected failures. |

For example, callers that separately validate an order, reserve stock, and handle a failed save can call one order-placement operation. Keep failure outcomes visible to callers. Verify what happens when reservation succeeds and saving fails. Prefer the design that requires the least caller knowledge while keeping failure handling and deployment practical.

Move observable assertions to the new interface before removing old tests. Keep coverage of behaviors that still have independent callers.

Adapted from [Matt Pocock's codebase design guides](https://github.com/mattpocock/skills/tree/5863806dd4e15c63174bee4e7515a4256792ecfa/skills/engineering/codebase-design).
