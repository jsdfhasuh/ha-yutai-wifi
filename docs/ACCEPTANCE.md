# Acceptance Boundaries

Current version: 0.1.1. Validation date: 2026-11-11.

## Idle Polling Regression

Initial 0.1.0 commissioning succeeded but sustained polling failed. A read-only
real-device reproduction confirmed: initial read succeeds, the same client after
65 seconds times out, and explicit MiIO handshake restores all five reads.
The no-command-retry policy had bypassed python-miio's usual timestamp/discovery
resynchronization on retry. Version 0.1.1 explicitly handshakes before each
identity/read-or-write operation while keeping relay write retries disabled.
Three synthetic regression cases cover idle reads, idle writes and recovery from
handshake failure. Sustained post-update live polling is a separate deployment check.

## Passed

- The initial 0.1.0 suite passed 43 tests against the real Home Assistant 2026.10.4 runtime, with
  synthetic devices and a fresh temporary configuration directory. This covers
  22 transport/model tests, 16 framework tests and 5 package tests.
- Model/MAC verification, explicit relay writes with acknowledgement and readback,
  duplicate devices, per-device state/IDs, reconfiguration, first refresh failures,
  cancellation serialization, unavailable readings and credential-free diagnostics
  are covered by those synthetic tests.
- A separate current-user DPAPI smoke probe used the actual reusable client on
  one JDLS1 device. Authenticated identity and all five local reads passed.
  The probe's transport rejects all methods except miIO.info and get_properties;
  zero write commands were sent. No credentials or device addresses are included here.
- Ruff lint/format and the explicit 16-file component package checks passed.
- Public source is available at https://github.com/jsdfhasuh/ha-yutai-wifi.
  CI run 43030347181 passed offline tests, HA framework tests, hassfest and HACS
  validation for component commit 01554a6. The shared python-miio dependency uses
  the minimum-version policy required by hassfest.
- HACS custom-repository download and installation succeeded on HA 2026.10.4.
  All 16 installed component files matched the approved source byte-for-byte.
  The HA configuration check passed, and the config flow created one loaded
  entry with five available entities. No relay write was sent during commissioning.
- Initial live verification found no removed preexisting entries/entities or
  changes to preexisting config-entry data. Related logs contained no errors.
- The earlier protocol research completed one authorized ON/OFF/readback test,
  but that was not a test of this installed HA integration.

## Not Yet Accepted

- Tagged GitHub Releases and HACS default-store inclusion. Installation currently
  tracks the main branch; this is a custom repository, not a default-store entry.
- HACS upgrades to a different component version and uninstallation.
- Long-term restart/recovery reliability beyond initial commissioning checks.
- Its switch service controlling a real electrical load from HA.
- Multiple physical JDLS1 devices running concurrently; isolation is tested with fixtures.
- Long-duration availability, full WAN isolation, clock/power-cycle behavior,
  metering precision and the energy accumulation/reset period.
- Other models or native timer/protection/child-lock setting writes.

## Deployment Boundary

Earlier framework tests used only installed libraries in a temporary directory.
The subsequently authorized live installation used HACS and HA's config-flow
API, with private backups first. It installed only this component and its new
device entry/entities; it did not directly edit `.storage`, change production
YAML or call switch services. Configuration checking passed. Existing credentials
were transferred through SSH stdin, never through command-line values or public files.

Future public releases and production changes require appropriate confirmation.
Before installation, back up the affected integration/configuration
state, install only this domain, check HA configuration, and restart only HA
if required to load new integration code. Configuration and startup perform
read-only probes; the first real switch action remains a separate acceptance step.
