# Acceptance Boundaries

Local development version: 0.1.0. Validation date: 2026-11-11.

## Passed

- 43 tests passed against the real Home Assistant 2026.10.4 runtime, with
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
- Ruff lint/format and the explicit 14-file component package checks passed.
- The earlier protocol research completed one authorized ON/OFF/readback test,
  but that was not a test of this installed HA integration.

## Not Yet Accepted

- Public GitHub repository, published version/tag, and release assets.
- Official hassfest and HACS CI runs. Workflows are prepared but have not run.
- Actual HACS custom-repository download, installation, update or removal.
- Loading this integration into a running production HA instance.
- Its switch service controlling a real electrical load from HA.
- Multiple physical JDLS1 devices running concurrently; isolation is tested with fixtures.
- Long-duration availability, full WAN isolation, clock/power-cycle behavior,
  metering precision and the energy accumulation/reset period.
- Other models or native timer/protection/child-lock setting writes.

## Deployment Boundary

Framework tests used only installed libraries in a temporary directory; the
production HA configuration, config entries, entity registry, services and
container lifecycle were not changed. No production YAML check or restart was
needed because no HA configuration was modified. Dependency installation was
not performed inside the production environment.

Public upload and production installation require separate confirmation.
For the first installation, back up the affected integration/configuration
state, install only this domain, check HA configuration, and restart only HA
if required to load new integration code. Configuration and startup perform
read-only probes; the first real switch action remains a separate acceptance step.
