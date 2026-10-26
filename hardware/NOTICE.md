# Hardware provenance

`Net4MSX.pretty/W5100S_Net4CPC.kicad_mod`, the embedded U2 footprint, its module
pin assignments and corresponding generator data adapt the
`W5100S-NETWORK-MODULE` package/deviceset from:

- Net4CPC by salafek: https://github.com/salafek/Net4CPC
- Commit `f7e94b6ba940795f73feeddc7042d385615f9e4a`, `Net4CPC.sch`
- Repository license: GNU GPL version 3, retained in
  [LICENSES/Net4CPC-GPL-3.0.txt](LICENSES/Net4CPC-GPL-3.0.txt).

Changes: conversion from EAGLE to KiCad coordinates and format, new reference
and value text, KiCad pad dimensions and assignment of provisional SPI nets.
Unassigned pad numbers 13–20 are retained. This adapted material is distributed
under GPL-3.0; no broader license for unrelated original project work is implied.

The MSX logical pin table and contact geometry reference MSXDiagCartridge,
commit `cba9c736fc455b0212352f9a1c999c79959dfad2`, its Rev D schematic and top/bottom
copper Gerbers. Its MIT notice is retained in
[LICENSES/MSXDiagCartridge-MIT.txt](LICENSES/MSXDiagCartridge-MIT.txt).
The carrier outline is new, provisional geometry, not an imported board outline.

Pico and W5100S 3D models are simple original geometric placeholders. No vendor
STEP files, firmware or ESP8266 source have been copied into this repository.
