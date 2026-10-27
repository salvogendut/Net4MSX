# Reassessment using ESP8266-UNAPI-Firmware

## Architectural consequence

The ESP8266 project demonstrates a useful division: a Z80 UNAPI front end and a
network coprocessor exchanging compact binary commands and responses. This makes
a Pico that owns the W5100S sockets, DNS and DHCP a serious alternative to putting
all service code on the Z80. Evaluate that design first for software feasibility;
retain direct parallel access as the simpler hardware comparison. A transparent
SPI bridge offers less software relief than an actual command coprocessor.

The W5100S, MSX connector and TCP/IP UNAPI objective remain unchanged. The
previous documents were a requirements baseline, not completed implementation:
no existing firmware or qualified hardware needs to be discarded.

## Evidence and transferability

| Inspected evidence | Application to Net4MSX |
| --- | --- |
| Documentation: requested binary responses rather than unsolicited network payload | Use host-initiated receive and bounded transfers; a slow MSX must be able to pause |
| Regular requests carry command and big-endian length; responses carry status and optional data | Use explicit framing and document byte order per field; the wire protocol is distinct from the Z80 ABI |
| `SendResponse` and `CUSTOM_F_RETRY_TX` replay the last response | Distinguish retrieving a lost response from re-executing a send/open/close command |
| Header defines a 2148-byte command buffer; README requires a 2 KiB receive buffer or a sufficiently fast host | Size the complete path for the slowest consumer, or chunk transfers; do not assume a stock MSX can drain a stream continuously |
| Capability code reports four shared connections | Reuse the accounting concept, with W5100S DNS/DHCP reservations added explicitly |
| README links separate ROM and RAM Z80 drivers | Now pinned and reviewed in [Software review](SOFTWARE-REVIEW.md); their integration patterns need transport, API and licensing review before reuse |

## Behaviors that must not be copied unchanged

- The firmware calls ESP8266 WiFi/Arduino networking, storage, update and TLS
  facilities. A Pico/W5100S backend needs its own driver and services; this is
  an architectural reference, not a compilable Pico port.
- Documentation explicitly describes blocking DNS and no firmware `DNS_S`
  command, with results cached by the host driver. TCP/IP UNAPI 1.1 permits
  advertised blocking DNS/TCP-open and TLS; the earlier assessment incorrectly
  placed those features beyond 1.1. Net4MSX prefers asynchronous DNS and defers
  TLS as project choices. See the [source-backed correction](SOFTWARE-REVIEW.md#correction-to-the-earlier-unapi-assessment).
- `TCPIP_DNS_Q_NEW=206` is a private transport command, not a replacement for
  public UNAPI function 6. Function 0, discovery, unsupported functions and
  `TCPIP_WAIT` still need host-side behavior.
- The protocol documentation and code are not interchangeable. For example,
  the query table says `Ok`, but the parser writes `OK`; response formats also
  vary by command. Any compatibility mode needs captured fixtures and a
  command-by-command review, not just copied enum values.
- The generic receive path accepts a 16-bit input length before reading into
  its fixed array, without a visible capacity check on that path. A new parser
  must reject oversized frames before copying and reserve terminator space.
- Startup/reset code prints banners and `Ready`. The no-unsolicited-data design
  goal does not eliminate startup bytes; define reset synchronization explicitly.
- Last-response storage includes a pointer to payload data. A new design must
  guarantee the replay buffer's lifetime and immutability until acknowledgment
  or expiration, including while background services run.

## Revised proof of concept

The [companion-driver and ioLibrary review](SOFTWARE-REVIEW.md) completes the
initial source inspection. It finds useful discovery, workspace and replay
patterns, plus backend register/ring code, but no complete bounded transport or
service implementation ready for Net4MSX.

First implement or simulate one bounded request/response transaction, version and
capability negotiation, a TCP send/receive exchange and DNS start/status. Measure
Z80 workspace, ROM footprint, host transfer overhead and recovery behavior. Then
compare against the direct-parallel path before freezing bus hardware.

For the command path, reserve short bus accesses for mailbox/FIFO/status work;
network latency must not hold an MSX bus cycle in `/WAIT`. Define busy/ready,
buffer ownership, sequence or replay rules, reset invalidation and timeout
recovery. Test partial/oversized frames, lost responses, duplicate requests, host
pauses and resets during a transfer. These are planned tests, not completed ones.

Wi-Fi setup, ESP firmware updating and TLS certificate handling do not become
Net4MSX requirements. TLS remains outside the initial scope.
