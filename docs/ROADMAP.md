# Development roadmap

## 0. Reference baseline

- [x] Inspect Net4CPC's interface, schematic structure and BOM.
- [x] Inspect core/TCP-IP UNAPI specifications and ROM discovery example.
- [x] Inspect MSXDiagCartridge Rev D schematic and record connector signals.
- [x] Record source revisions and provisional architecture.
- [x] Inspect ESP8266 firmware and document host/coprocessor implications.
- [x] Select Net4CPC's generic module footprint for the user's SPI/parallel module concept.
- [x] Record WIZnet datasheet/errata revisions and [integration requirements](W5100S.md).
- [x] Inspect and pin the ESP8266 project's companion ROM/RAM Z80 drivers.
- [x] Inspect and pin the WIZnet ioLibrary candidate, including license, blocking
  behavior and SPI callbacks; record findings in [Software review](SOFTWARE-REVIEW.md).
- [x] Draft the [command-coprocessor/direct-parallel resource comparison](RESOURCE-BUDGET.md),
  distinguishing source evidence, allocation targets and unmeasured costs.
- [x] Draft [bounded transport, backpressure, response replay and reset recovery](MAILBOX-PROTOCOL.md).
- [ ] Validate the draft with a host-side protocol model and fake socket backend:
  malformed frames, credit boundaries, duplicate side effects, ACK and reset races.
- [ ] Build minimal Z80/Pico and direct-access software to replace ROM/RAM
  allocations with linked maps and stack measurements before architecture selection.
- [ ] Resolve source reuse/licensing and define adaptations for the reviewed
  timeout, DNS/DHCP parser and UDP semantic issues before importing code.
- [ ] Select the exact module and minimum target MSX configuration.
- [ ] Resolve bus mapping, Pico role, ROM/workspace strategy and toolchain.

Exit: a reviewed interface specification with addresses, electrical assumptions,
module pinout and a complete ownership model for memory and hardware sockets.

## 1. Interface concept and electrical prototype

- [x] Generate editable KiCad interface/placement concept using Net4CPC's module footprint.
- [ ] Review the 3D concept against the physical module and cartridge enclosure.
- [ ] Draw the MSX decode, buffering, power and reset schematic.
- [ ] Complete the concept KiCad interface skeleton with actual bus/ROM/power circuitry.
- [ ] Confirm the physical module against the reference footprint before routing.
- [ ] Trace module mode straps and reset/power circuitry; resolve the vendor
  input-voltage discrepancy before approving an unshifted MSX connection.
- [ ] Build a register-access diagnostic and a prototype interface.
- [ ] Verify reset, register read/write, indirect addressing and data transfers.
- [ ] For SPI, verify first-byte/inter-byte read timing against erratum 1 with
  single-byte and burst patterns; record clocks, waveform evidence and errors.
- [ ] Measure timing, power and bus release; verify no response when unselected.
- [ ] For the Pico path, prove mailbox transfers and boot synchronization without
  holding a bus cycle for network processing; qualify FIFO storage/count crossing,
  the 22-GPIO allocation and fail-safe reset gating from the draft budget.

Exit: repeatable register tests and captured electrical evidence on a named MSX
and module revision. A schematic review alone does not satisfy this milestone.

## 2. UNAPI integration

- [ ] Choose reproducible assembler/build tooling and implement ROM initialization.
- [ ] Implement discovery, information, capabilities and defined unsupported calls.
- [ ] Implement and verify the per-function transport-failure mapping, local
  numeric DNS/result state and slot-safe caller-buffer copies.
- [ ] Validate hook chaining, workspace allocation and expanded-slot behavior.
- [ ] Check coexistence with another UNAPI implementation and normal DOS boot.

Exit: discoverable provider with correct ABI and no boot/memory regressions.

## 3. Static-IP networking

- [ ] Implement socket allocation, bounded commands, TCP and UDP data paths.
- [ ] Implement static configuration, mandatory numeric address parsing and DNS.
- [ ] Validate real clients and repeated connection lifecycle tests.
- [ ] Exercise buffer boundaries, exhaustion, link loss and remote failure.
- [ ] Verify every allocated socket, UDP metadata/payload wrap, truncation followed
  by another datagram, and receive progress after interrupt acknowledgment.
- [ ] For the Pico path, inject partial/oversized commands, lost responses,
  duplicate requests, slow host reads and resets during transfers.

Exit: repeatable TCP and UDP transfers plus DNS lookup, with documented limits
and truthful capability reporting. Record client versions and test setup.

## 4. Configuration and recovery

- [ ] Implement DHCP, lease renewal and internal socket arbitration.
- [ ] Add configuration persistence, MAC-address provisioning and reset recovery.
- [ ] Evaluate passive TCP and optional ICMP/configuration capabilities.

Exit: stable startup, renewal and recovery without leaking application resources.

## 5. Cartridge release candidate

- [ ] Produce editable schematic/layout, reviewed BOM and manufacturing outputs.
- [ ] Validate footprint orientation and shell/RJ45 fit with a physical prototype.
- [ ] Qualify named MSX machines, slot expanders and supported CPU speeds.
- [ ] Publish reproducible firmware build and hardware qualification evidence.

Exit: assembled cartridge meets the declared compatibility matrix. Keep emulator,
bench and physical-machine results distinct. Decide project licensing before
distributing derived hardware or source; retain upstream notices when importing.
