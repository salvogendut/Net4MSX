# Net4MSX

An MSX cartridge project providing Ethernet through a **W5100S module** and a
**TCP/IP UNAPI** driver. A Raspberry Pi Pico is an optional candidate for bus
interfacing or supporting firmware; it is not yet a required component.

The project is at the architecture stage, with design requirements, an editable
KiCad concept and a 3D placement mockup. Firmware and a routed, qualified PCB
remain to be developed.

## Starting design

- Compare Net4CPC-style direct parallel access with a Pico command coprocessor,
  informed by ESP8266-UNAPI-Firmware's small Z80 front end.
- Expose TCP/IP UNAPI 1.1 to MSX applications, using the W5100S socket engine.
- Use MSXDiagCartridge as the connector, ROM and mechanical reference.
- Use Net4CPC's generic SPI/parallel module footprint as requested for the user's
  W5100S module. Confirm its physical pinout before completing the circuit.

## Documentation

- [Architecture and decisions](docs/ARCHITECTURE.md)
- [Hardware requirements and cartridge pinout](docs/HARDWARE.md)
- [UNAPI implementation scope](docs/UNAPI.md)
- [Development roadmap and acceptance criteria](docs/ROADMAP.md)
- [Reference repositories and provenance](docs/REFERENCES.md)
- [ESP8266 firmware reassessment](docs/ESP8266-REASSESSMENT.md)
- [KiCad concept and 3D mockup](hardware/README.md)

The first milestone is to select the module and MSX register mapping, then prove
reliable register access on a prototype. No assembler, firmware SDK, or build
commands have been selected yet.
