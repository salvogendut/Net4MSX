# Mailbox model and conformance tests

The executable host-side model validates the logical contract in
[Mailbox protocol](MAILBOX-PROTOCOL.md). It uses Python's standard library and
a fake socket backend. It neither connects to a network nor accesses a Pico,
MSX, serial port or W5100S. Firmware and interface circuitry remain unimplemented.

From the repository root, with Python 3.10 or newer:

```sh
python3 -m unittest discover -s tests -v
```

No third-party dependencies or KiCad installation are required for these tests.
The existing hardware checker is a separate tool with separate dependencies.

## Model structure

| File | Responsibility |
| --- | --- |
| [codec.py](../tools/mailbox/codec.py) | Header, CRC, call records, limits and marshaling validation |
| [device.py](../tools/mailbox/device.py) | Eight registers, two 16-byte FIFOs, streaming parser, session/ACK/replay state and reset |
| [backend.py](../tools/mailbox/backend.py) | Three application sockets, fixed 2 KiB rings and observable logical effects |
| [host.py](../tools/mailbox/host.py) | Credit-aware transfers, bounded polls, response validation and at most two rewinds |
| [test_mailbox.py](../tests/test_mailbox.py) | Conformance scenarios, corruption/reset injection and seeded transfer schedules |
| [Handshake fixtures](../tests/fixtures/mailbox-v1.json) | Exact bytes published in the protocol document |
| [CRC collision fixture](../tests/fixtures/mailbox-crc-collision.json) | Different request data with equal frame CRCs |

Each `Mailbox.tick()` is one bounded scheduler visit. It can consume one input
FIFO byte and produce one output FIFO byte. The host and test harness explicitly
decide when to tick and when to read/write registers; accesses do not wait for
network processing. A tick has **no physical time duration**.

The device owns two fixed 2,100-byte frame arrays and a 16-byte parser header
scratch area. A first request streams into its retained buffer; a duplicate is
compared against that buffer byte by byte. ACKs use header/CRC scratch and do not
overwrite the retained request. `assert_bounds()` checks FIFO, frame and socket
ring limits. Python objects, temporary codec copies and test instrumentation are
not included in those logical storage counts; these tests do not measure the
Pico's proposed 32 KiB SRAM budget or the Z80's 512-byte workspace target.

Backend execution and response publication occur in separate visits. Reset can
therefore interrupt before an action or after the action but before its reply.
Reset clears socket and transport ownership, while test-only effect counters and
event history survive so an uncertain action remains visible to assertions.
TCP events record enqueue, and UDP events record a logical datagram send; they
are not captured Ethernet packets.

The fake implements the modeled portions of public functions 8–18: UDP
open/close/state/send/receive and TCP open/close/abort/state/send/receive. TCP
opens start in SYN-SENT; the harness supplies peer establishment/FIN events.
Graceful close retains allocation until the simulated peer finishes, while
abort frees it immediately. Ephemeral ports are chosen deterministically within
the specified range for repeatable tests; this is not a production random-port
implementation. Unknown model opcodes return transport status 1, not a claim
about the future provider's public `ERR_NOT_IMP` behavior.

## Behaviors checked

| Area | Observable acceptance conditions |
| --- | --- |
| Wire representation | Published handshake bytes, register byte order, CRC, length bounds, reserved fields and pointer-field rejection |
| Input validation | Invalid frames and partial requests cannot open a socket or enqueue data; oversized headers fault before collecting a body |
| Backpressure | FIFO counts stay within 0–16, overflow/empty-read faults latch, producer/consumer pauses preserve data |
| Replay | Duplicates during execution and after publication cause one backend action; complete request bytes remain immutable |
| CRC collision | Two distinct valid frames with the same CRC produce a conflicting-duplicate fault rather than being mistaken for a replay |
| ACK | Reading the last byte does not release storage; repeated ACKs preserve the next exchange; ACK can arrive while RX is full |
| Host recovery | Lost/truncated/corrupt replies rewind without resubmitting the request; persistent failure stops after three read attempts; wrong identity is fatal |
| Reset | Collection, execution, committed-but-unpublished reply, replay/control and partial ACK all lose session ownership; resident sockets close too |
| Counters | Old/future session/sequence values are rejected; sequence and host session counters never silently wrap |
| TCP | Whole-buffer enqueue or `ERR_BUFFER`, 0/512/2,048/2,049-byte boundaries, RX snapshot, ring wrap and replay |
| UDP | 0/1/1,472/1,473-byte boundaries, sender metadata, original length on truncation, DE=0 consumption, whole-datagram removal and ring wrap |
| Allocation | Three shared application handles, no service-socket allocation, transient/resident close rules and exhaustion |
| Failure bounds | Stuck execution and backend failures require reset; a shared host polling budget cannot replenish itself after each byte or retry |

The seeded schedule tests interleave FIFO writes, reads and service visits for
maximum-size TCP requests. They check bounds on every visit and compare the
accepted payload and effect count. They are repeatable scenario tests, not an
exhaustive model checker or proof of all possible interleavings.

The host model uses an overall polling ceiling and a configurable reply-idle
limit (128 visits by default) to detect a retained reply that stops producing
bytes. An idle expiry permits rewind within the same overall budget; it does
not resubmit an uncertain operation. Its visit counts are test policy, not a
calibrated Z80 delay or a replacement for the protocol's firmware deadlines.

## Protocol clarifications from the model

- Accepting the current ACK must flush any unread RX FIFO tail as it releases
  the response. Otherwise stale bytes could prefix the next response. An old,
  repeated ACK must leave the current FIFO and read cursor untouched.
- A frame declaring more bytes than have arrived is incomplete, not yet a CRC
  error. It remains suspended without effects until completed or reset. Lengths
  beyond the maximum are rejected immediately after the header.
- Reply retention and backend progress are independent. A full RX FIFO cannot
  block ACK input, and a paused host must not grow another response queue.
- CRC equality is insufficient to identify a duplicate. The collision fixture
  exercises the draft's requirement to compare every request byte.

These clarify the existing wire version; they do not change header layout,
register offsets or the handshake vectors.

## Remaining qualification

This is a transport model and selected socket-semantic fake, not the complete
UNAPI provider. It does not implement DNS/DHCP packet parsers, service-socket
arbitration, configuration, all capability/error-precedence combinations,
slot switching, hook chaining, CPU register preservation or caller-buffer copies.
The host returns Python transport exceptions; the per-function UNAPI failure
translation still belongs to the Z80 front end.

The fake's ring wrap is byte storage behavior, not W5100S register ordering,
interrupt acknowledgment or SPI erratum qualification. Its service counter
shows that visits continue during a host pause; it does not demonstrate a real
DNS lookup, DHCP renewal or hardware watchdog. Clock crossing, bus timing,
electrical reset gating, real network deadlines and physical zero-length UDP
transmission all remain hardware/firmware acceptance work.

Next, select reproducible build tools and implement a minimal Z80 front end and
Pico transport/backend skeleton. Reuse the wire fixtures and fault scenarios
against those implementations, record linked ROM/RAM maps and stack usage,
then qualify the physical interface. Keep the direct-parallel comparison open
until that evidence replaces the [resource allocations](RESOURCE-BUDGET.md).
