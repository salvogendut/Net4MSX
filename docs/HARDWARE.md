# Hardware investigation

## Editable concept

The [KiCad concept and 3D mockup](../hardware/README.md) use Net4CPC's generic
W5100S SPI/parallel module footprint, selected by the user, and an optional Pico
command-coprocessor layout. They establish placement and interface pin mapping;
bus, power and ROM circuitry and copper routing remain to be implemented.

## W5100S interface

Net4CPC uses an indirect parallel bus with these four offsets, also specified in
section 5.2 of the [W5100S datasheet v1.2.8](https://docs.wiznet.io/img/products/w5100s/w5100s-ds-v128e.pdf):

| Offset | Register | Role |
| --- | --- | --- |
| 0 | MR | Mode register |
| 1 | IDM_ARH | Indirect address, high byte |
| 2 | IDM_ARL | Indirect address, low byte |
| 3 | IDM_DR | Indirect data |

Its EAGLE schematic and BOM show 74LS30/74LS32 decode logic, a 3.3 V regulator
and alternative module footprints. Reuse the interface concept; redesign the
decode for MSX. The W5100S fixes indirect mode and auto-increment on; see the
[vendor integration notes](W5100S.md#host-access-and-hardware-review). Confirm the
module's straps and reset circuit, and qualify the bus timing on the prototype.

The W5100S has four shared hardware sockets and 16 KiB of TX/RX storage. It
operates at 3.3 V; WIZnet advertises 5 V I/O tolerance, but the
[voltage-rating discrepancy](W5100S.md#host-access-and-hardware-review) needs
resolution before approving direct MSX drive. No module power-input rating follows
from that claim. It does not support IP fragmentation. See the
[WIZnet overview](https://docs.wiznet.io/Product/Chip/Ethernet/W5100S).

The [SPI read erratum](W5100S.md#spi-read-erratum) is a requirement for the Pico
transport study. Qualify first-byte and inter-byte timing, including burst/DMA
transfers, before accepting register-access reliability.

The original Pico's RP2040 requires a 3.3 V GPIO design; provide appropriate
translation from the MSX bus. Validate output thresholds in the reverse
direction and output-enable sequencing. Consult the
[RP2040 electrical specifications](https://datasheets.raspberrypi.com/rp2040/rp2040-datasheet.pdf).

The [mailbox proposal](MAILBOX-PROTOCOL.md#bus-contract) requires two 16-byte
hardware FIFOs and eight host register offsets. Its [GPIO budget](RESOURCE-BUDGET.md#gpio-and-hardware-cost)
uses 22 of the original Pico's 26 exposed GPIO, assuming external decode/FIFO
logic. That logic, translation, ROM and reset gating are additional circuitry;
the present pin map and CAD have not been changed to implement the proposal.

## Cartridge connector reference

The following is transcribed from `CONN1` in MSXDiagCartridge's
`PCB/schematic/simpleCart_RevD.pdf`, visually inspected at the revision recorded
in [References](REFERENCES.md). Slash prefixes below identify active-low control
signals. This is logical connector numbering, **not a component-side view or
an approved footprint**. Check edge orientation and continuity against the
reference Gerbers and a physical cartridge before routing.

| Pin | Signal | Pin | Signal |
| --- | --- | --- | --- |
| 1 | /CS1 | 26 | A13 |
| 2 | /CS2 | 27 | A1 |
| 3 | /CS12 | 28 | A0 |
| 4 | /SLTSL | 29 | A3 |
| 5 | Reserved | 30 | A2 |
| 6 | /RFSH | 31 | A5 |
| 7 | /WAIT | 32 | A4 |
| 8 | /INT | 33 | D1 |
| 9 | /M1 | 34 | D0 |
| 10 | /BUSDIR | 35 | D3 |
| 11 | /IORQ | 36 | D2 |
| 12 | /MERQ (memory request) | 37 | D5 |
| 13 | /WR | 38 | D4 |
| 14 | /RD | 39 | D7 |
| 15 | /RESET | 40 | D6 |
| 16 | Reserved | 41 | GND |
| 17 | A9 | 42 | CLOCK |
| 18 | A15 | 43 | GND |
| 19 | A11 | 44 | SW1 |
| 20 | A10 | 45 | +5 V |
| 21 | A7 | 46 | SW2 |
| 22 | A6 | 47 | +5 V |
| 23 | A12 | 48 | +12 V |
| 24 | A8 | 49 | SOUNDIN |
| 25 | A14 | 50 | -12 V |

The reference uses slot selection for ROM chip enable and selectable output
enable paths for full-address or page-specific ROM visibility. Its page windows
are `4000h–7FFFh` (/CS1), `8000h–BFFFh` (/CS2), and `4000h–BFFFh` (/CS12).
The new cartridge must gate its own ROM and peripheral accesses explicitly.

## Requirements before a schematic is frozen

- Select an exact W5100S module, obtain its schematic and confirm it exposes
  the desired parallel or SPI interface. Record connector numbering, supply,
  regulator arrangement, reset and mode straps.
- Budget slot current, regulator dissipation and startup load, including the
  optional Pico. Use +5 V and ground; leave unused rails/signals unconnected
  unless a reviewed circuit requires them. Preserve reserved pins.
- Define bus direction, read/write qualification, reset state and high-impedance
  behavior when unselected. Review `/BUSDIR`, `/WAIT` and `/INT` electrical
  requirements against MSX bus documentation before wiring them.
- Measure data setup/hold, read access, write pulses and bus release at the
  intended CPU speed. Validate any wait-state circuit rather than relying on
  firmware latency assumptions.
- Apply the recorded WIZnet datasheet/errata baseline to reset, interface timing
  and module review. Resolve electrical ambiguities and capture register-access
  evidence before freezing the circuit; see [W5100S integration](W5100S.md).
- Specify ROM visibility, peripheral window, workspace storage, write protection
  and boot recovery. Include coexistence with expanded slots in the review.
- Derive the edge footprint and board outline from Gerbers plus measurements;
  verify thickness, contact geometry, bevel, mounting holes and shell clearance.
  The reference README identifies Konami-style shell holes and warns that IC
  sockets can exceed available height. An Ethernet module/RJ45 needs its own fit
  check and cable-access plan.
- Include local decoupling and accessible power, reset, select and bus test points.

The concept records provisional module pin assignments and board dimensions.
None is fabrication-qualified; MSX port allocation is still undecided.
