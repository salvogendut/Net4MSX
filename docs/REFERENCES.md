# Reference baseline

Inspected on 2026-10-26. The paths supplied in the project brief resolve in this
environment under `/home/sbognann/Development`, rather than beside Net4MSX.
The cartridge checkout is named `MSXDiagCartridge` (case-sensitive).

| Reference | Inspected commit | Files used |
| --- | --- | --- |
| [Net4CPC](https://github.com/salafek/Net4CPC/tree/f7e94b6ba940795f73feeddc7042d385615f9e4a) | `f7e94b6ba940795f73feeddc7042d385615f9e4a` | `README.md`, `Net4CPC.sch`, `bom.txt` |
| [MSX-UNAPI-specification](https://github.com/salvogendut/MSX-UNAPI-specification/tree/eb7e978c4c2133bf5d31a470281940f5ee44c4f5) | `eb7e978c4c2133bf5d31a470281940f5ee44c4f5` | `docs/`, `examples/unapi-rom.asm`, examples/tools inventory |
| [MSXDiagCartridge](https://github.com/salvogendut/MSXDiagCartridge/tree/cba9c736fc455b0212352f9a1c999c79959dfad2) | `cba9c736fc455b0212352f9a1c999c79959dfad2` | `README.md`, `PCB/schematic/simpleCart_RevD.pdf`, Gerber inventory |
| [ESP8266-UNAPI-Firmware](https://github.com/salvogendut/ESP8266-UNAPI-Firmware/tree/bc37fc18a42c7e37705412abebf03e598f1bac5d) | `bc37fc18a42c7e37705412abebf03e598f1bac5d` | `README.md`, `documentation/README.md`, `UNAPI8266.h`, command parser/response/capability/DNS paths in the `.ino` |

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

Its companion Z80 drivers live outside this checkout and still require inspection
and revision pinning before reuse:

- [ROM driver](https://github.com/ducasp/MSX-Development/tree/master/MSX-SM/WiFi/UNAPI_BIOS_CUSTOM_ESP_FIRMWARE)
- [RAM driver](https://github.com/ducasp/MSX-Development/tree/master/MSX-SM/WiFi/UNAPI_DRIVER_CUSTOM_ESP_FIRMWARE)
- [Configuration utility](https://github.com/ducasp/MSX-Development/tree/master/MSX-SM/WiFi/CFG8266)

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

- [W5100S overview](https://docs.wiznet.io/Product/Chip/Ethernet/W5100S): sockets,
  host interfaces, supply/I/O characteristics and protocol limitations.
- [W5100S documentation](https://docs.wiznet.io/Product/Chip/Ethernet/W5100S/document):
  obtain and pin the datasheet and errata revision used for schematic sign-off.
- [RP2040 datasheet](https://datasheets.raspberrypi.com/rp2040/rp2040-datasheet.pdf):
  electrical and timing requirements if the original Pico is selected.

These component links can change independently of the pinned Git repositories.
Record the exact module schematic and component document revisions with the
eventual hardware design.
