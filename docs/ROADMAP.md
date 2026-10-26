# Development roadmap

## 0. Reference baseline

- [x] Inspect Net4CPC's interface, schematic structure and BOM.
- [x] Inspect core/TCP-IP UNAPI specifications and ROM discovery example.
- [x] Inspect MSXDiagCartridge Rev D schematic and record connector signals.
- [x] Record source revisions and provisional architecture.
- [x] Inspect ESP8266 firmware and document host/coprocessor implications.
- [x] Select Net4CPC's generic module footprint for the user's SPI/parallel module concept.
- [ ] Inspect and pin the ESP8266 project's companion ROM/RAM Z80 drivers.
- [ ] Compare command-coprocessor and direct-parallel software/resource budgets.
- [ ] Specify bounded transport, backpressure, response replay and reset recovery.
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
- [ ] Build a register-access diagnostic and a prototype interface.
- [ ] Verify reset, register read/write, indirect addressing and data transfers.
- [ ] Measure timing, power and bus release; verify no response when unselected.
- [ ] For the Pico path, prove mailbox transfers and boot synchronization without
  holding a bus cycle for network processing.

Exit: repeatable register tests and captured electrical evidence on a named MSX
and module revision. A schematic review alone does not satisfy this milestone.

## 2. UNAPI integration

- [ ] Choose reproducible assembler/build tooling and implement ROM initialization.
- [ ] Implement discovery, information, capabilities and defined unsupported calls.
- [ ] Validate hook chaining, workspace allocation and expanded-slot behavior.
- [ ] Check coexistence with another UNAPI implementation and normal DOS boot.

Exit: discoverable provider with correct ABI and no boot/memory regressions.

## 3. Static-IP networking

- [ ] Implement socket allocation, bounded commands, TCP and UDP data paths.
- [ ] Implement static configuration, mandatory numeric address parsing and DNS.
- [ ] Validate real clients and repeated connection lifecycle tests.
- [ ] Exercise buffer boundaries, exhaustion, link loss and remote failure.
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
