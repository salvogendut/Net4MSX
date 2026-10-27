# Architecture resource budgets

Draft comparison, 2026-10-27. Continue with a **Pico command-coprocessor
prototype**, while retaining direct W5100S indirect-parallel access as the
comparison. The Pico moves service RAM and scheduling off the MSX, but needs a
mailbox circuit, two software targets and reset/replay handling. This is a
prototype recommendation, not a hardware selection or firmware-size measurement.

The [mailbox proposal](MAILBOX-PROTOCOL.md) supplies the numerical limits below.
Both candidates use the same three-application/one-service socket policy,
2 KiB TX/RX per hardware socket, IPv4 and 1,500-byte IP datagram limit. TLS,
raw IP and passive TCP remain outside the first networking prototype.

## Evidence versus allocations

| Item | Evidence | What it does not establish |
| --- | --- | --- |
| Reference ESP ROM | Supplied image is 16,384 bytes; reserves 30 new workspace bytes plus existing slot work | Size of a Net4MSX ROM, mailbox buffers, stack or slot-copy code |
| Reference ESP RAM driver | One 16 KiB mapper segment and RAM helper | Minimum RAM requirement for a ROM cartridge |
| W5100S | Four sockets; 8 KiB TX and 8 KiB RX; proposed 2 KiB each per socket | DNS/DHCP storage, host workspace or a fifth application socket |
| Original non-wireless Pico | 264 KiB SRAM, 2 MiB onboard flash and 26 exposed GPIO | Available pins after wiring or firmware fit |
| Current KiCad concept | Pico GP16–21 assigned to six W5100S signals | A connected or qualified MSX mailbox, ROM, decode or power circuit |

Source evidence: [pinned software review](SOFTWARE-REVIEW.md),
[W5100S integration notes](W5100S.md), [current pin map](../hardware/pin-map.csv)
and Raspberry Pi's [Pico specification][pico] (consulted 2026-10-27).
All remaining sizes below are **engineering allocations**, chosen to make the
prototype reviewable. They are neither compiler outputs nor estimates derived
from the ESP ROM's 30-byte workspace.

## MSX ROM and RAM

Start both builds with a 16 KiB cartridge-ROM target. For a memory-mapped mailbox
or indirect-register window carved out of that page, subtract respectively
eight or four bytes from the addressable ROM area, including any aliases that
the eventual decoder introduces. Reserve roughly 4 KiB of the page as growth
margin; the first linked build must establish whether code fits. If direct
network services exceed that target, compare a 32 KiB banked ROM against a
smaller feature set rather than silently assuming bank switching is free.
The Pico also needs a separate firmware image; ROM savings do not remove that.

### Pico front-end workspace target: 512 bytes

| Allocation | Bytes | Purpose |
| --- | ---: | --- |
| Saved ABI registers, frame metadata and copy scratch | 64 | Stream frames without retaining a second complete payload on MSX |
| Slot-switch/copy trampoline | 64 | Access caller memory hidden by cartridge ROM; code and temporary state |
| Session, sequence, counters and ownership | 32 | One serialized exchange |
| Handle records | 64 | Four 16-byte entries; three application entries plus bookkeeping |
| Configuration, capability and DNS-result snapshot | 64 | Local queries and transport-loss behavior |
| Private stack | 128 | Initial nesting budget; needs a measured high-water mark |
| Alignment, hook bookkeeping and growth reserve | 96 | Explicit contingency |
| **Total** | **512** | Proposed persistent page-3 allocation |

The host copies names/payloads in bounded pieces; it does not need a 256-byte
DNS name buffer or 2 KiB replay buffer. Replay storage is in Pico SRAM. Slot
changes and copy code must work when the caller's source/destination overlaps
the ROM page. The 64-byte trampoline and 128-byte stack are acceptance targets,
not proven sufficient implementations. Resize explicitly if the first build
exceeds them. Existing BIOS slot work, the caller's own buffers/stack and any
RAM helper are outside this new allocation and must not be double-counted as
free application memory.

### Direct-parallel workspace target: 6 KiB

| Allocation | Bytes | Purpose |
| --- | ---: | --- |
| Network configuration, four socket records and timers | 512 | Z80 owns allocation and backend state |
| DNS | 1,024 | 256-byte name, 512-byte packet, 256-byte parser/query state |
| Future DHCP | 2,048 | 1,536-byte bounded packet buffer and 512-byte lease/parser state |
| Slot-copy scratch and hook state | 256 | ROM/caller visibility and serialization |
| Private stack | 512 | Service parsing and nested driver calls; measure actual use |
| Alignment and implementation growth reserve | 1,792 | Unmeasured assembly/C-port cost |
| **Total** | **6,144** | Full DNS/DHCP design allocation |

A static-IP-plus-DNS build can omit the 2 KiB DHCP allocation, yielding a
4 KiB target with the same contingency. Hardware rings supply TCP/UDP payload
storage; no extra per-socket 2 KiB host buffers are assumed. Direct access has no
transport replay buffer, but still needs atomic pointer updates and bounded
register operations. A parser that requires additional packet copies must
account for them explicitly.

Neither target specifies the minimum MSX RAM size or safe allocator yet. Prove
BASIC/DOS boot order, page-3 availability, expanded slots, hook chaining and
stack bounds before choosing that compatibility claim. A RAM-loaded development
driver additionally occupies its own code segment and possibly helper storage;
that is separate from these ROM-provider workspace targets.

## Pico memory and execution budget

Use static allocations, one active core and an autonomous service loop for the
first experiment. No RTOS, heap, filesystem, USB console or second-core stack is
assumed in this budget. Adding any of them requires an updated map.

| SRAM allocation | Bytes |
| --- | ---: |
| Retained request and response, each rounded from 2,100 to 2,112 bytes | 4,224 |
| Framing, ACK/duplicate parser scratch and transport state | 256 |
| Four socket records, 128 bytes each | 512 |
| DNS name/packet/state | 1,024 |
| Future DHCP packet/lease/parser state | 2,048 |
| SPI transfer scratch | 256 |
| Network configuration and counters | 256 |
| Bounded diagnostic log | 1,024 |
| SDK, driver globals and other runtime allowance | 16,384 |
| Core-0 stack | 4,096 |
| Alignment and growth reserve | 2,688 |
| **Target SRAM ceiling** | **32,768** |

This leaves 232 KiB of the Pico's nominal 264 KiB outside the proposed ceiling;
it is headroom, not additional advertised network buffering. The request buffer
is also TX staging; the response buffer is also RX/replay staging. Do not add
another full packet buffer implicitly in a backend wrapper or DMA path.
The 32 bytes of bidirectional bus FIFO storage are separate hardware storage.

Use a 256 KiB flash target: 160 KiB code, 32 KiB constants, 32 KiB
boot/configuration allowance and 32 KiB growth margin. The rest of the 2 MiB
flash is unallocated. This does not promise a bootloader, persistent settings,
dual-image updates or an SDK build of that size. Record `.text`, `.rodata`,
initialized data, BSS, load image, stack high-water and any heap use from the
first linked build; initialized data counts toward both flash and RAM.

DNS's 512-byte packet allocation is an initial classic-DNS profile, not a
license to accept oversized replies. Handle truncation and compression safely;
do not advertise EDNS or TCP fallback. DHCP's 1,536 bytes is a new proposed
receive capacity, not the reviewed ioLibrary's 552-byte message structure.
Both parsers need length checks and separate retained state even though their
socket is shared. See [Software review](SOFTWARE-REVIEW.md#iolibrary-backend-assessment).

## GPIO and hardware cost

The budget is for the original non-wireless Pico already depicted in the
concept. It assumes an external interface handles address decoding and FIFO
timing; it does not wire all MSX address/control signals to Pico pins.

| Pico function | GPIO | Notes |
| --- | ---: | --- |
| W5100S SPI | 4 | MISO, MOSI, SCK, CS; concept GP16–19 |
| W5100S reset and interrupt | 2 | Concept GP20–21 |
| Interface data bus | 8 | Bidirectional, on the 3.3 V side |
| Interface register selection | 3 | Up to eight Pico-side registers; distinct from MSX address decode |
| Interface read, write and select | 3 | Direction/transfer qualification |
| Interface attention/reset-event input | 1 | Pending FIFO work or latched MSX reset; reasons read from interface |
| Firmware-ready output | 1 | Fail-safe gating/flush on Pico restart; default low |
| **Assigned / spare** | **22 / 4** | Out of 26 exposed GPIO |

The sixteen Pico-side interface signals fit the twenty GPIO left after W5100S.
A possible grouping is GP0–7 data, GP8–10 selection, GP11–13 strobes/select,
GP14 attention and GP15 ready, leaving GP22/26/27/28 spare. This is an allocation
sketch only; no pin-map or CAD change has been made. SWD uses its separate debug
pads. Optional interrupt output, debug UART or clock lines spend the spare pins.
Validate any PIO pin grouping, state machines and DMA channels when the interface
implementation is chosen.

| Hardware block | Pico coprocessor | Direct parallel |
| --- | --- | --- |
| W5100S/module | SPI plus reset/interrupt, six Pico GPIO | D0–7, A0–1, CS/RD/WR and reset/interrupt: fifteen signals plus mode straps |
| MSX address decode and bus isolation | Required; mailbox window and mutually exclusive ROM enable | Required; four indirect registers and mutually exclusive ROM enable |
| Level translation | MSX-to-interface path and reverse thresholds must be qualified | Resolve WIZnet voltage-rating discrepancy and qualify both directions |
| Mailbox storage/control | Two 16-byte hardware FIFOs, counts, reset/control latches and clock crossing | Not required |
| ROM and write protection | Required independently of Pico firmware | Required; banking is a possible extra cost |
| Power/reset | Module, Pico, interface logic, watchdog/boot gating | Module and bus/ROM logic; reset still requires qualification |
| Recoverable programming | ROM plus Pico firmware/debug connector | ROM programmer/update path |

The GPIO count is not a component count or BOM price. A CPLD, discrete FIFOs,
buffers or dual-port-memory solution has not been selected. The existing board
has none of this bus glue. Power/current, regulator loss, startup sequencing,
MSX read access time and output-disable time remain **unmeasured for both**.
Do not infer slot-current compliance from the Pico's spare SRAM or pin count.

## Transfer and scheduling costs

For one data transfer of N bytes, a normal request and response each carry a
16-byte header, 32-byte call record and four-byte CRC; an ACK carries 20 bytes.
Thus **N + 124 bytes** cross the mailbox data register in a successful exchange,
before FIFO-count/status polling, slot switching, CRC computation or retries.

| Application payload N | Mailbox data-register bytes | Payload fraction |
| ---: | ---: | ---: |
| 0 | 124 | 0% |
| 64 | 188 | 34.0% |
| 512 | 636 | 80.5% |
| 1,472 | 1,596 | 92.2% |
| 2,048 | 2,172 | 94.3% |

These are framing arithmetic, not throughput results. Polling costs at least
one credit/count check per available burst and may involve many empty polls.
Pico-to-W5100S SPI transfers and copies add another stage; the SPI read erratum
limits usable timing. Overlap may help throughput but cannot be assumed.

Direct indirect access needs two address-register writes followed by N data
accesses for one contiguous region, plus socket-state/pointer/command work and
another setup at ring wrap. It avoids mailbox framing and the MCU copy, while
leaving DNS/DHCP processing and synchronization on the Z80. Neither count is a
cycles-per-byte measurement. The chip's 100 Mbit/s link and 70 MHz SPI headline
are not application throughput predictions.

For each prototype, measure 64/512/1,472/2,048-byte transfers, status polling,
ring wrap and slot-copy paths at the named MSX clock. Report payload bytes/s,
Z80 cycles or busy time, maximum interrupt-disabled interval, command latency,
and recovery latency. For the Pico also record FIFO stall time, scheduler
latency and SPI clock/delay waveforms. Keep transport benchmarks separate from
network peer latency and actual TCP/UDP throughput.

## Decision gates

| Gate | Pico evidence required | Direct-parallel evidence required |
| --- | --- | --- |
| Memory fit | Linked host ROM, 512-byte workspace target, Pico flash/RAM/stack map | Linked ROM and 4 KiB static/DNS or 6 KiB DHCP-inclusive workspace target |
| Bus feasibility | Hardware FIFO timing, clock crossing, reset gating, no network-dependent wait states | Qualified indirect address/data cycles and bus release |
| Correctness | Mailbox fault/replay tests plus UNAPI fixtures and SPI erratum coverage | UNAPI fixtures, serialized indirect access and bounded service progress |
| Services | Autonomous DNS/DHCP progress during host pauses | Bounded timer/WAIT scheduling without hook or caller-memory corruption |
| Cartridge cost | Actual interface BOM, power and enclosure fit | Actual decode/buffering/possible ROM-banking BOM, power and fit |

The [protocol model and conformance fixtures](MAILBOX-MODEL.md) now exercise
bounded logical storage, one execution under retries, atomic TCP enqueue and
whole-datagram UDP consumption with a fake backend. Next, build a reproducible
minimal Z80 front end and Pico backend to replace these allocations with
measured maps. Revisit direct parallel
if mailbox electrical complexity, ROM fit or measured transfer cost outweighs
the benefit of moving services off the MSX.

## Validation of this draft

Checked local documentation links/anchors and reference labels, summed the
memory/GPIO tables, and verified frame sizes, datagram limits and transfer
overhead arithmetic. The mailbox's three handshake byte fixtures were decoded
and their CRCs checked with both a bitwise implementation of the specified
algorithm and Python's `zlib.crc32`.

Those were document/format consistency checks. The subsequent
[model qualification](MAILBOX-MODEL.md) adds executable transport tests, but
does not supply a Z80/Pico build, stack measurement, network runtime test or
electrical qualification. Those acceptance cases remain work for the prototype.

[pico]: https://www.raspberrypi.com/products/raspberry-pi-pico/
