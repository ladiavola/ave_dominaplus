ave_dominaplus — v1.5.0

Highlights
- Support for dimmers (non-RGBW). Thanks to @jean_coqs and @bisi77 for the contribution.
- Support for shutters. Thanks to @jean_coqs and @0xmtb for the contribution.
- Support for scenarios.
- Gracefully handles reconnection after webserver disconnections
- Entities now grouped in devices
- Optional: expose on/off devices as lights instead of switches (may require reconfiguration).
- AVEbus address exposed as an extra attribute for each related entity.

Under the hood
- Deferred Home Assistant state writes during startup to avoid a runtime error when entities are attached.
- Improved device discovery: the integration now recovers bus addresses for devices.
- Migration groundwork for a more reliable entity unique-ID scheme; newly added device families already use the new IDs.
- 99% test coverage and general improvements on the integration quality scale