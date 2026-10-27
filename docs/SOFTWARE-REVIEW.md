# Software reference review

Reviewed on 2026-10-27. The companion Z80 drivers provide useful MSX integration
patterns, and WIZnet's W5100S driver is a plausible Pico backend. Neither is ready
to import unchanged. The main adaptation work is bounded transport, service
scheduling, public UNAPI semantics and failure recovery.

This review supports continuing the Pico command-coprocessor feasibility study;
it does not select that architecture over direct parallel access. Source-derived
observations are separated below from Net4MSX recommendations and measurements.

## Pinned sources

| Source | Repository revision | Reviewed scope |
| --- | --- | --- |
| [Companion ROM driver][rom] | `ducasp/MSX-Development` at `20fcedf1377b1ea3d1346e87e5bf7cc42ebe2c76` | `MSX-SM/WiFi/UNAPI_BIOS_CUSTOM_ESP_FIRMWARE`: assembly, README, supplied ROM size |
| [Companion RAM driver][ram] | Same revision | `MSX-SM/WiFi/UNAPI_DRIVER_CUSTOM_ESP_FIRMWARE`: assembly and README |
| [WIZnet ioLibrary][iolibrary] | `Wiznet/ioLibrary_Driver` at `e1791974e76d0b00cbac9e349ed92477b8d41386` | `Ethernet/W5100S`, `wizchip_conf`, `socket`, `Internet/DNS`, `Internet/DHCP`, license notices |

These are repository commit pins, not release numbers. The ROM source declares
implementation 1.3 and API 1.2; the RAM source identifies driver 1.1 and API 1.1.
The repository's latest commit message concerns other driver variants and should
not be used to describe these two directories. The separate ESP8266 firmware
remains pinned as recorded in [References](REFERENCES.md); protocol compatibility
between the snapshots has not been tested.

## Reuse assessment

| Candidate | Useful material | Net4MSX adaptation |
| --- | --- | --- |
| ROM front end | Cartridge header, slot discovery, EXTBIO chaining, function dispatch, deferred workspace allocation | Revalidate hooks/slots and allocation; remove Wi-Fi menus, RTC and SM-X port dependencies |
| RAM front end | RAM-helper installation, mapper allocation, numeric IPv4 parsing, receive replay | Suitable development reference if mapped RAM is an accepted requirement; not a minimum-machine assumption |
| ESP transport | Explicit command lengths, host-requested receive, replay of a lost response | Replace UART assumptions with a bounded mailbox protocol; define reset and replay ownership |
| W5100S low-level C driver | Register access, stable size reads, buffer address calculation and ring wrap | Add platform callbacks, verified SPI timing and bounded recovery |
| ioLibrary sockets/services | Socket state flows, DNS/DHCP packet and service examples | Translate API semantics and replace blocking paths; validate parser bounds and service resource ownership |

## Z80 integration and resource evidence

Both drivers implement case-insensitive `TCP/IP` discovery through `DE=2222h`,
dispatch functions 0–29, preserve registers for undefined functions, and chain
previous EXTBIO and timer hooks. These are useful patterns to compare with the
normative UNAPI examples. The ROM also writes the adjacent DISINT/ENAINT hook
area, so coexistence review must extend beyond EXTBIO.
[ROM initialization and dispatch][rom-hooks], [RAM installation][ram-install].

| Resource | Observed evidence | Limit of the observation |
| --- | --- | --- |
| ROM image | Supplied `ESP8266.rom` is 16,384 bytes; source origin is `4000h` | Includes setup/UI code; not a measured size for a minimal Net4MSX front end |
| ROM workspace | `HIMEM_RESERVED_SIZE=30`, plus the slot's existing eight-byte work area | Does not include mailbox staging, stack or any new Net4MSX state |
| ROM setup scratch | Setup borrows the BASIC program area | Exclude that UI from the proposed minimal front end |
| RAM driver residency | Installs into one 16 KiB mapper segment at `4000h`; requires the UNAPI RAM helper | DOS 2 allocates a system segment; DOS 1 uses the last primary-mapper segment |
| RAM DNS storage | `DNS_BUFFER` reserves 256 bytes and `DNS_RESULT` four bytes inside the resident segment | Additional variables, helper memory and stack also exist |

The ROM defers high-memory allocation until its provider is requested, avoiding
allocation before later disk ROM initialization. That is a useful design lesson,
not proof that the same allocator is safe for every BASIC/DOS/expanded-slot
combination. The RAM driver has writable code and resident state, including a
self-modified comparison instruction in its response matcher; moving that code
into ROM requires adaptation. [ROM memory design][rom], [RAM source][ram].

Neither inspected directory provides a reproducible assembler/build recipe.
The source and supplied ROM were not rebuilt or compared byte-for-byte. A target
toolchain, stack budget and minimum MSX configuration remain open.

## Z80 behavior that needs adaptation

- **Transport coupling:** both use UART ports `06h`/`07h`; the ROM also uses the
  SM-X `F2h` device and an optional FPGA quick-receive path. Bulk `OUTI`/`OTIR`
  loops assume the transport can accept the stream. Net4MSX must specify credits,
  transfer bounds and host pauses rather than copy these port numbers or timing.
- **DNS:** the RAM driver parses numeric addresses locally and sends command 6
  for server lookup. The ROM sends private command 206 with flags and the name.
  Both then wait for the reply, with a 900-tick response counter, and cache a
  result for function 7. That is up to 15 seconds at 60 Hz or 18 seconds at 50 Hz
  if timer interrupts keep advancing. It is not an asynchronous service loop.
  [ROM DNS][rom-dns], [RAM DNS][ram-dns].
- **Timeout coverage:** runtime waits commonly use `H_TIMI` counters, despite
  the READMEs describing operation without interrupts. The RAM `VER_ESP*`
  startup loops poll for bytes without a timeout check. Lost startup/version
  replies and stopped timer progress need explicit recovery tests.
  [RAM startup/version handling][ram-version].
- **Replay:** TCP/UDP receive can request retransmission with `'r'`, with up to
  three retries. This retrieves a response after the network receive has already
  happened. Preserve that distinction, but add transaction identity, immutable
  response lifetime, acknowledgment and reset invalidation. The reviewed path
  does not establish replay protection for arbitrary open/send/close commands.
  [RAM receive replay][ram-replay], [ROM receive replay][rom-replay].
- **Boundary handling:** the ROM scans DNS names until a terminator without an
  explicit maximum, and `TCPIP_TCP_SEND` enters its block-output loop without a
  zero-count guard. Validate these cases before reusing transfer code. The RAM
  driver has a bounded name-copy path, but it still needs boundary fixtures.
  [ROM DNS][rom-dns], [ROM TCP send][rom-send], [RAM DNS][ram-dns].
- **Progress and capabilities:** both map function 29 to a success return, with
  interrupts enabled by the dispatch entry. A Net4MSX implementation that relies
  on host-driven service progress needs a real processing step. Capability flags
  must describe our backend rather than relay ESP firmware answers unchanged.

### Correction to the earlier UNAPI assessment

The pinned TCP/IP UNAPI specification explicitly introduces blocking DNS/TCP-open
feature flags and TLS support in **version 1.1**. These features are not inherently
outside our selected API version. See its [capability definitions][unapi-caps]
and [change log][unapi-history]. The ROM's advertised API 1.2 still must not be
inherited without reviewing that version's contract.

Net4MSX continues to prefer asynchronous DNS and bounded progress, and continues
to defer TLS. Those are project choices. A future blocking implementation would
need a deliberate behavior decision and truthful capability reporting, not an
automatic API-version upgrade.

## ioLibrary backend assessment

The pinned configuration defaults to W6300. Defining `_WIZCHIP_=W5100S` selects
the W5100S branch and its standard SPI path. Its indirect-bus branch is selected
inside `wizchip_conf.h`; it was inspected but not compiled in this review.
[Configuration][wiz-config].

Register critical-section and chip-select callbacks with
`reg_wizchip_cris_cbfunc` and `reg_wizchip_cs_cbfunc`, and SPI byte/burst callbacks
with `reg_wizchip_spi_cbfunc` and `reg_wizchip_spiburst_cbfunc`. The W5100S routines
hold selection across a frame and delegate actual data movement to those
callbacks. There is no explicit first-data/inter-byte delay in the reviewed SPI
read path. The platform implementation must satisfy the [SPI erratum](W5100S.md#spi-read-erratum),
including burst completion before deselection. This absence is a porting
requirement, not evidence that every existing platform violates the timing.
[Read paths][wiz-read], [callback registration][wiz-callbacks].

For indirect access, also review nested critical-section/chip-select behavior
around `setMR` and register both byte and buffer bus callbacks. Do not treat the
legacy attempts to clear `MR.AI` as disabling the W5100S's fixed auto-increment.

### Scheduling and public API mismatches

| Area | Source observation | Required adaptation |
| --- | --- | --- |
| Nonblocking sockets | `SF_IO_NONBLOCK` avoids some waits, but command-register polling remains; `sendto` still waits for SENDOK/TIMEOUT after issuing SEND | Split command issue/completion and impose host-side deadlines, including when hardware stops responding |
| Register helpers | Stable 16-bit size reads retry; MDIO helpers and chip-ticker delay poll hardware | Bound retries/recovery in the platform design |
| UDP receive | `recvfrom` retains the unconsumed portion in `sock_remained_size` | UNAPI receive must discard the tail on truncation and report the original datagram length |
| UDP send/zero lengths | `sendto` can clamp length to TX capacity; shared argument checks reject zero lengths | Translate limits/errors explicitly; implement UNAPI zero-length behavior rather than silently changing payloads |
| Ownership | Socket routines accept a hardware socket index; socket/service state is global | Add one allocator for application handles and internal DNS/DHCP sockets; serialize shared state |

Evidence: [socket implementation][wiz-sockets], [low-level helpers][wiz-helpers],
and [UNAPI UDP receive semantics][unapi-udp]. Hardware retry registers do not
bound a software poll if the bus or device is stuck.

### DNS and DHCP

`DNS_run` opens its supplied socket in blocking mode and loops until a result or
timeout; `DNS_time_handler` must advance once per second. It uses a caller-owned
256-byte message buffer by default and 192-byte local name arrays
(`MAX_DOMAIN_NAME=128`, `MAXCNAME=192`). These are partial storage figures, not a
total stack/RAM budget. The query builder uses `strcpy` into the local name array;
the reply name parser does not receive the packet's end pointer. Length,
compression-pointer and reply-validation review is required before reuse.
[DNS implementation][wiz-dns], [DNS configuration][wiz-dns-h].

For the preferred asynchronous design, use bounded query/start/status/cancel
states. Preserve query length separately from receive length: the reviewed
`DNS_run` reassigns `len` during receive polling and also uses it for retries.
Do not assume the sample retry path is already suitable.

`DHCP_run` offers a recurring state machine with lease maintenance and a one-second
timer. However, its leased-address conflict path calls blocking `sendto` and waits
for two timer ticks after DECLINE. It also temporarily changes the common `RCR`,
and initialization clears network settings. Those effects must be coordinated
with application sockets. [DHCP implementation][wiz-dhcp].

DHCP's message layout is 552 bytes (`236 + OPT_SIZE`, with `OPT_SIZE=312`). That
is not a safe receive-buffer recommendation by itself: `parseDHCPMSG` forwards
the available RX size to `recvfrom` without checking the supplied buffer's
capacity, then parses options. Define capacity checks, minimum packet size and
option bounds before adoption. DNS/DHCP each retain a global socket and buffer
pointer; simultaneous operation needs distinct ownership or deliberate scheduling.

## License and provenance findings

| Material | Observed notices | Reuse consequence |
| --- | --- | --- |
| Z80 companion drivers | Repository `LICENSE` contains GPLv3; assembly/README notices require publishing changes and credit Oduvaldo Pavan Junior, with DenyoNet/Konamiman ancestry and KdL contributions | Record the applicable terms and ancestry before importing source; do not classify these files as permissive or assume the separate ESP firmware license applies |
| ioLibrary | Root `license.txt` contains MIT terms; the inspected C/header files retain BSD-style three-clause notices | Preserve both the root license and applicable file notices when importing/distributing; GitHub's MIT label alone is incomplete provenance |
| Separate ESP8266 firmware | Previously pinned repository declares LGPL-2.1-or-later | Keep its provenance distinct from the companion drivers |

Sources: [Z80 root license][z80-license], [ROM notices][rom], [RAM notices][ram],
[ioLibrary root license][wiz-license], [representative W5100S file notice][wiz-hal].
The companion READMEs also describe restrictions on an older custom ESP firmware;
that text is not a license for either ioLibrary or our separately pinned firmware
checkout. Any imported subset needs an explicit notice/license inventory. This
review imports no upstream source and does not select a license for Net4MSX.

## Consequences for the architecture comparison

| Candidate | What this review establishes | What remains to measure/design |
| --- | --- | --- |
| Pico owns W5100S | A small persistent Z80 workspace is plausible for a command front end; register/ring code is available in C | Mailbox/FIFO circuitry, GPIO and electrical budget, bounded services/replay, actual ROM/RAM and transfer measurements |
| Z80 owns W5100S through indirect parallel access | The same register/ring algorithms are useful references | Z80 service implementation or C-port cost, socket allocator, DNS/DHCP storage, workspace and bus timing |

The 30-byte ROM workspace and ioLibrary buffer constants cannot be combined into
a complete Net4MSX budget. No firmware has been selected or imported. For the next
interface proposal, carry forward explicit transfer credits/length limits,
transaction replay and reset epochs, single ownership of hardware state, and
independent deadlines for transport and network operations. Public I/O addresses
remain unassigned.

The follow-on [mailbox proposal](MAILBOX-PROTOCOL.md) and
[resource comparison](RESOURCE-BUDGET.md) now specify those draft limits and
ownership rules. Their allocation targets supplement the evidence above;
they are not linked firmware measurements or a decision to import these sources.

## Validation performed

- Retrieved 23 selected upstream blobs into a temporary review directory and
  verified each against its Git blob SHA and recorded size at the pinned commits.
- Measured the supplied ROM image length; did not establish source/binary parity.
- Ran this host syntax check from the pinned ioLibrary root with GCC 12.2.0:

```sh
gcc -std=c99 -Wall -Wextra -Werror=implicit-function-declaration \
  -D_WIZCHIP_=W5100S -I Ethernet -fsyntax-only \
  Ethernet/W5100S/w5100s.c Ethernet/wizchip_conf.c Ethernet/socket.c \
  Internet/DNS/dns.c Internet/DHCP/dhcp.c
```

It exited successfully with warnings about unused parameters, a partially
initialized callback structure and pointer-to-32-bit casts in the DNS query
builder on the 64-bit host. This checks parsing of the selected SPI configuration;
it is not a Pico link/build, a Z80 build, runtime testing or electrical evidence.
Other observations above are source review findings and need targeted tests when
an implementation is chosen.

[rom]: https://github.com/ducasp/MSX-Development/blob/20fcedf1377b1ea3d1346e87e5bf7cc42ebe2c76/MSX-SM/WiFi/UNAPI_BIOS_CUSTOM_ESP_FIRMWARE/ESP8266.asm
[ram]: https://github.com/ducasp/MSX-Development/blob/20fcedf1377b1ea3d1346e87e5bf7cc42ebe2c76/MSX-SM/WiFi/UNAPI_DRIVER_CUSTOM_ESP_FIRMWARE/ESP8266.asm
[iolibrary]: https://github.com/Wiznet/ioLibrary_Driver/tree/e1791974e76d0b00cbac9e349ed92477b8d41386
[rom-hooks]: https://github.com/ducasp/MSX-Development/blob/20fcedf1377b1ea3d1346e87e5bf7cc42ebe2c76/MSX-SM/WiFi/UNAPI_BIOS_CUSTOM_ESP_FIRMWARE/ESP8266.asm#L499-L602
[ram-install]: https://github.com/ducasp/MSX-Development/blob/20fcedf1377b1ea3d1346e87e5bf7cc42ebe2c76/MSX-SM/WiFi/UNAPI_DRIVER_CUSTOM_ESP_FIRMWARE/ESP8266.asm#L78-L370
[rom-dns]: https://github.com/ducasp/MSX-Development/blob/20fcedf1377b1ea3d1346e87e5bf7cc42ebe2c76/MSX-SM/WiFi/UNAPI_BIOS_CUSTOM_ESP_FIRMWARE/ESP8266.asm#L2881-L3101
[ram-dns]: https://github.com/ducasp/MSX-Development/blob/20fcedf1377b1ea3d1346e87e5bf7cc42ebe2c76/MSX-SM/WiFi/UNAPI_DRIVER_CUSTOM_ESP_FIRMWARE/ESP8266.asm#L1170-L1469
[ram-version]: https://github.com/ducasp/MSX-Development/blob/20fcedf1377b1ea3d1346e87e5bf7cc42ebe2c76/MSX-SM/WiFi/UNAPI_DRIVER_CUSTOM_ESP_FIRMWARE/ESP8266.asm#L3414-L3466
[ram-replay]: https://github.com/ducasp/MSX-Development/blob/20fcedf1377b1ea3d1346e87e5bf7cc42ebe2c76/MSX-SM/WiFi/UNAPI_DRIVER_CUSTOM_ESP_FIRMWARE/ESP8266.asm#L1862-L1922
[rom-replay]: https://github.com/ducasp/MSX-Development/blob/20fcedf1377b1ea3d1346e87e5bf7cc42ebe2c76/MSX-SM/WiFi/UNAPI_BIOS_CUSTOM_ESP_FIRMWARE/ESP8266.asm#L3491-L3545
[rom-send]: https://github.com/ducasp/MSX-Development/blob/20fcedf1377b1ea3d1346e87e5bf7cc42ebe2c76/MSX-SM/WiFi/UNAPI_BIOS_CUSTOM_ESP_FIRMWARE/ESP8266.asm#L4328-L4363
[unapi-caps]: https://github.com/salvogendut/MSX-UNAPI-specification/blob/eb7e978c4c2133bf5d31a470281940f5ee44c4f5/docs/TCP-IP%20UNAPI%20specification.md#L367-L384
[unapi-history]: https://github.com/salvogendut/MSX-UNAPI-specification/blob/eb7e978c4c2133bf5d31a470281940f5ee44c4f5/docs/TCP-IP%20UNAPI%20specification.md#L2310-L2351
[unapi-udp]: https://github.com/salvogendut/MSX-UNAPI-specification/blob/eb7e978c4c2133bf5d31a470281940f5ee44c4f5/docs/TCP-IP%20UNAPI%20specification.md#L1131-L1148
[wiz-config]: https://github.com/Wiznet/ioLibrary_Driver/blob/e1791974e76d0b00cbac9e349ed92477b8d41386/Ethernet/wizchip_conf.h#L77-L167
[wiz-read]: https://github.com/Wiznet/ioLibrary_Driver/blob/e1791974e76d0b00cbac9e349ed92477b8d41386/Ethernet/W5100S/w5100s.c#L100-L328
[wiz-callbacks]: https://github.com/Wiznet/ioLibrary_Driver/blob/e1791974e76d0b00cbac9e349ed92477b8d41386/Ethernet/wizchip_conf.c#L289-L417
[wiz-sockets]: https://github.com/Wiznet/ioLibrary_Driver/blob/e1791974e76d0b00cbac9e349ed92477b8d41386/Ethernet/socket.c
[wiz-helpers]: https://github.com/Wiznet/ioLibrary_Driver/blob/e1791974e76d0b00cbac9e349ed92477b8d41386/Ethernet/W5100S/w5100s.c#L330-L497
[wiz-dns]: https://github.com/Wiznet/ioLibrary_Driver/blob/e1791974e76d0b00cbac9e349ed92477b8d41386/Internet/DNS/dns.c
[wiz-dns-h]: https://github.com/Wiznet/ioLibrary_Driver/blob/e1791974e76d0b00cbac9e349ed92477b8d41386/Internet/DNS/dns.h#L65-L103
[wiz-dhcp]: https://github.com/Wiznet/ioLibrary_Driver/blob/e1791974e76d0b00cbac9e349ed92477b8d41386/Internet/DHCP/dhcp.c
[z80-license]: https://github.com/ducasp/MSX-Development/blob/20fcedf1377b1ea3d1346e87e5bf7cc42ebe2c76/LICENSE
[wiz-license]: https://github.com/Wiznet/ioLibrary_Driver/blob/e1791974e76d0b00cbac9e349ed92477b8d41386/license.txt
[wiz-hal]: https://github.com/Wiznet/ioLibrary_Driver/blob/e1791974e76d0b00cbac9e349ed92477b8d41386/Ethernet/W5100S/w5100s.c#L1-L43
