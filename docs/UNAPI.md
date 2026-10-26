# TCP/IP UNAPI implementation plan

Target core UNAPI 1.1 and TCP/IP UNAPI 1.1, API identifier `TCP/IP`. The local
specification and ROM/RAM examples are authoritative for discovery, calling
conventions and hook chaining; see [References](REFERENCES.md).

The ESP8266 firmware adds a concrete host/coprocessor reference; see
[Reassessment](ESP8266-REASSESSMENT.md). Evaluate its companion Z80 drivers before
writing the front end from scratch. Keep their transport conventions separate
from the public API and do not inherit blocking DNS, TLS flags or private command
206 under our pinned 1.1 contract. The function coverage below applies to the
combined Z80/Pico implementation if that architecture is selected.

## Discovery and ABI

- Implement EXTBIO discovery (`DE=2222h`) with case-insensitive identifier
  matching, enumeration and correct chaining to other implementations.
- Function 0 returns the implementation identity/version and API version 1.1.
- Dispatch all 30 defined functions (0–29). Optional functionality is represented
  through capability flags and the specified errors, including `ERR_NOT_IMP`.
- Undefined function numbers follow the core UNAPI register-preservation rule;
  do not treat them as ordinary defined-but-unsupported calls.
- Follow each routine's registers, buffer rules, flags and error precedence.
  Handle page-1 visibility and caller buffers explicitly for a ROM provider.
- Keep capabilities truthful throughout bring-up. A discovery-only prototype
  is not evidence of networking support.

## Function coverage roadmap

All rows below are planned; nothing is implemented yet.

| Functions | Area | Initial goal / later work |
| --- | --- | --- |
| 0 | Implementation information | Identity and versions |
| 1–3 | Capabilities, IP information, network state | Accurate capabilities, configuration and link state |
| 4–5 | ICMP echo | Defer until W5100S socket-less behavior is mapped to UNAPI |
| 6–7 | DNS query and result | Numeric IPv4 parsing first, then asynchronous DNS lookup |
| 8–12 | UDP open/close/state/send/receive | Datagram boundaries, buffer limits and socket accounting |
| 13–18 | TCP open/close/abort/state/send/receive | Active connections first; evaluate passive modes separately |
| 19 | TCP output discard | Defer; advertise only if semantics can be met |
| 20–24 | Raw IP | Defer; report unsupported capability |
| 25 | Automatic configuration | DHCP after static networking works |
| 26 | Manual IP configuration | Local address, mask, gateway and DNS configuration |
| 27 | TTL / ToS | Evaluate individual get/set capabilities |
| 28 | Automatic ping reply configuration | Evaluate against hardware behavior |
| 29 | Wait / processing step | Correct progress semantics and interrupts enabled on return |

Numeric IPv4 parsing in `TCPIP_DNS_Q` is required even without DNS-server lookup
support. Optional features do not imply that every call to their routine can
unconditionally return `ERR_NOT_IMP`; consult the per-parameter requirements.

## Socket and service model

The four hardware sockets form a shared pool, not four TCP plus four UDP
connections. DNS/DHCP may need internal UDP resources. Choose and document
reservation or arbitration before reporting connection counts. UNAPI handles
must be validated and mapped to owned sockets; reopening must not expose stale
state or leak resources.

DNS and DHCP require software even with hardware TCP/IP offload. Define timeouts,
retries, cancellation and DHCP lease renewal. `TCPIP_WAIT` may be a no-op only
when no software processing step depends on it; hardware offload alone does not
establish that once software services are present.

W5100S states and command completion are inputs to a UNAPI state machine, not
the public ABI. Explicitly handle connection failure, remote close, graceful
close versus abort, send capacity, RX ring wrap, zero-length datagrams and
receive truncation according to the specification. Report datagram limits and
fragmentation capabilities that the implementation actually supports.

## Verification

Use the reference `APILIST`, TCP/IP utility sources and example consumers to
check discovery and capability reporting. Add driver tests for register ordering,
ring wrap, socket exhaustion, invalid handles, errors and reset cleanup once the
implementation exists. Test real UNAPI clients against controlled TCP/UDP/DNS
services, including cable removal, unavailable peers and repeated open/close.
An emulator can validate ROM integration, but cannot establish physical bus
timing or real W5100S interoperability without the corresponding hardware model.

For the coprocessor candidate, also validate framing limits, backpressure,
response replay without duplicate network actions, boot synchronization and
reset during transfer. Capture host/firmware protocol fixtures and check that
every advertised capability has the required public register-level behavior.
