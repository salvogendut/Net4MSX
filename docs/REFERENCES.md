# Reference baseline

Repository references inspected on 2026-10-26; the WIZnet documentation review
and companion-driver/ioLibrary source review were added on 2026-10-27.
The paths supplied in the project brief resolve in this
environment under `/home/sbognann/Development`, rather than beside Net4MSX.
The cartridge checkout is named `MSXDiagCartridge` (case-sensitive).

| Reference | Inspected commit | Files used |
| --- | --- | --- |
| [Net4CPC](https://github.com/salafek/Net4CPC/tree/f7e94b6ba940795f73feeddc7042d385615f9e4a) | `f7e94b6ba940795f73feeddc7042d385615f9e4a` | `README.md`, `Net4CPC.sch`, `bom.txt` |
| [MSX-UNAPI-specification](https://github.com/salvogendut/MSX-UNAPI-specification/tree/eb7e978c4c2133bf5d31a470281940f5ee44c4f5) | `eb7e978c4c2133bf5d31a470281940f5ee44c4f5` | `docs/`, `examples/unapi-rom.asm`, examples/tools inventory |
| [MSXDiagCartridge](https://github.com/salvogendut/MSXDiagCartridge/tree/cba9c736fc455b0212352f9a1c999c79959dfad2) | `cba9c736fc455b0212352f9a1c999c79959dfad2` | `README.md`, `PCB/schematic/simpleCart_RevD.pdf`, Gerber inventory |
| [ESP8266-UNAPI-Firmware](https://github.com/salvogendut/ESP8266-UNAPI-Firmware/tree/bc37fc18a42c7e37705412abebf03e598f1bac5d) | `bc37fc18a42c7e37705412abebf03e598f1bac5d` | `README.md`, `documentation/README.md`, `UNAPI8266.h`, command parser/response/capability/DNS paths in the `.ino` |
| [Companion Z80 drivers](https://github.com/ducasp/MSX-Development/tree/20fcedf1377b1ea3d1346e87e5bf7cc42ebe2c76) | `20fcedf1377b1ea3d1346e87e5bf7cc42ebe2c76` | ROM/RAM driver assembly and READMEs, root `LICENSE`; supplied ROM byte length |
| [WIZnet ioLibrary_Driver](https://github.com/Wiznet/ioLibrary_Driver/tree/e1791974e76d0b00cbac9e349ed92477b8d41386) | `e1791974e76d0b00cbac9e349ed92477b8d41386` | `Ethernet/W5100S`, `wizchip_conf`, `socket`, `Internet/DNS`, `Internet/DHCP`, root and file license notices |

Net4CPC establishes the W5100S indirect parallel interface and CPC-specific port
map. It is not an MSX electrical design. Its repository contains a GPL v3 license.

The UNAPI repository supplies the normative API behavior and implementation
examples. Its MIT license credits Néstor Soriano. Keep Ethernet UNAPI and TCP/IP
UNAPI scopes separate.

MSXDiagCartridge supplies the connector/ROM reference and shell guidance. Its MIT
license credits v9938. The Rev D PDF was visually inspected; Gerber geometry and
physical dimensions have not yet been measured or qualified for this project.

ESP8266-UNAPI-Firmware provides a practical command-coprocessor reference. The
inspected README marks it deprecated; this is a statement about that checkout,
not a reason to discard its protocol lessons. Source headers specify LGPL-2.1-or-later
and credit Oduvaldo Pavan Junior, with HTTP additions credited to Jeroen Taverne.
See [the reassessment](ESP8266-REASSESSMENT.md) for applicability and limitations.

Its companion Z80 drivers remain outside this checkout. They are now pinned and
reviewed in [Software review](SOFTWARE-REVIEW.md), including reuse candidates,
blocking behavior, storage evidence and license/provenance constraints:

- [ROM driver](https://github.com/ducasp/MSX-Development/tree/20fcedf1377b1ea3d1346e87e5bf7cc42ebe2c76/MSX-SM/WiFi/UNAPI_BIOS_CUSTOM_ESP_FIRMWARE)
- [RAM driver](https://github.com/ducasp/MSX-Development/tree/20fcedf1377b1ea3d1346e87e5bf7cc42ebe2c76/MSX-SM/WiFi/UNAPI_DRIVER_CUSTOM_ESP_FIRMWARE)
- [Configuration utility](https://github.com/ducasp/MSX-Development/tree/20fcedf1377b1ea3d1346e87e5bf7cc42ebe2c76/MSX-SM/WiFi/CFG8266): located, not reviewed in this step.

The Z80 repository includes GPLv3 and source-disclosure notices; its source also
credits inherited code. ioLibrary's root MIT license coexists with BSD-style
file headers. Preserve the applicable notices and settle reuse terms before
importing a subset; the review does not assign a project-wide license.

The hardware concept adapts Net4CPC's generic module footprint; its GPL v3 license
is retained under `hardware/LICENSES/`. Other firmware has not been vendored.
A license for original Net4MSX work has not yet been selected.

## User's module

The user identified [AliExpress item 4001260587995](https://it.aliexpress.com/item/4001260587995.html)
as a W5100S SPI/parallel module and explicitly selected Net4CPC's generic module
footprint for this concept. The listing was inaccessible during this session.
Its identity and pinout have not been independently verified from the listing;
the supplied footprint is the Net4CPC reference, not WIZ810SMJ.

## Component documentation

- [RP2040 datasheet](https://datasheets.raspberrypi.com/rp2040/rp2040-datasheet.pdf):
  electrical and timing requirements if the original Pico is selected.
- [Raspberry Pi Pico specification](https://www.raspberrypi.com/products/raspberry-pi-pico/):
  live manufacturer page consulted 2026-10-27 for the original Pico's 264 KiB
  SRAM, 2 MiB onboard flash and 26 exposed GPIO. Used in the
  [resource comparison](RESOURCE-BUDGET.md); these are component capacities,
  not measured Net4MSX firmware consumption.

### WIZnet documentation baseline

Reviewed on 2026-10-27 from the
[W5100S product page](https://docs.wiznet.io/Product/Chip/Ethernet/W5100S).
See [W5100S integration notes](W5100S.md) for project implications and known source
inconsistencies. Versions below identify the inspected documents, not hardware
qualification or a promise that upstream links will remain unchanged.

| Source | Inspected revision / scope |
| --- | --- |
| [Product overview](https://docs.wiznet.io/Product/Chip/Ethernet/W5100S) | Live page; capabilities and resource index |
| [Datasheet](https://docs.wiznet.io/img/products/w5100s/w5100s-ds-v128e.pdf) | v1.2.8, 2023-05-16; host interface, buffers, reset, electrical/timing requirements |
| [Errata](https://docs.wiznet.io/img/products/w5100s/w5100s-errata-en-v100.pdf) | v1.0.0, 2023-05-22; SPI read erratum 1 |
| [W5100S / W5100 comparison](https://docs.wiznet.io/img/products/w5100s/application/w5100svsw5100_cs_v110e.pdf) | v1.1.0, 2018-04-06; interface and register differences |
| [TCP function note](https://docs.wiznet.io/Product/Chip/Ethernet/W5100S/Application-Note/tcp) | Live page; initialization, state and buffer flows |
| [UDP function note](https://docs.wiznet.io/Product/Chip/Ethernet/W5100S/Application-Note/udp) | Live page; receive record format and send/timeout flows |
| [SOCKET-less command note](https://docs.wiznet.io/img/products/w5100s/application/w5100s_an_slc_v100e.pdf) | v1.0.0, 2018-05; ARP/PING sequencing |
| [Interrupt note](https://docs.wiznet.io/img/products/w5100s/application/w5100s_an_interrupt_v100e.pdf) | v1.0.0, 2018-04-01 per revision history; interrupt handling and transport exclusion |

SHA-256 of the datasheet and errata downloaded during this review:

```text
f24b0445acf355ce19873b304040c3479052d23917bce4bff4738578b5da1023  w5100s-ds-v128e.pdf
29e68d4eb60d17414be794be9689c812494532e365bef751c25fa647b0c9ae46  w5100s-errata-en-v100.pdf
```

The PDFs remain upstream; this repository contains project notes and links.
Recheck the errata and record the actual module schematic before electrical
sign-off. The chip documentation does not verify the AliExpress module pinout.

Software and hardware resources linked from the same page:

- [WIZnet ioLibrary_Driver](https://github.com/Wiznet/ioLibrary_Driver/tree/e1791974e76d0b00cbac9e349ed92477b8d41386):
  selected source layers now pinned and reviewed above. Adoption, platform port
  and runtime qualification remain pending; it is not a selected dependency.
- [Reference schematic, transformer version](https://github.com/Wiznet/Hardware-Files-of-WIZnet/blob/master/02_iEthernet/W5100S/Reference%20Schematic/W5100S_Ref_Schematic_V120_use_trans.pdf)
  and [integrated-magnetics version](https://github.com/Wiznet/Hardware-Files-of-WIZnet/blob/master/02_iEthernet/W5100S/Reference%20Schematic/W5100S_int_Ref_Schematic_V100.pdf):
  linked resources only; circuit review and revision pinning remain pending.
  Neither establishes the selected module's carrier footprint or regulator wiring.
