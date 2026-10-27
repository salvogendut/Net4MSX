"""Deterministic socket fake, not a TCP stack or a W5100S register emulator."""

from collections import Counter
from dataclasses import dataclass, field

from .codec import Call, MAX_DATA, MAX_UDP

OK, NOT_IMP, NO_NETWORK, NO_DATA, INV_PARAM = 0, 1, 2, 3, 4
NO_FREE, EXISTS, NO_CONN, CONN_STATE, BUFFER, LARGE_DGRAM = 9, 10, 11, 12, 13, 14


class BackendFailure(RuntimeError):
    """Injected controller failure, requiring session reset."""


class Ring:
    """Fixed 2 KiB storage with explicit wrap and occupancy."""

    def __init__(self):
        self.storage = bytearray(MAX_DATA)
        self.read_pos = self.write_pos = self.used = 0

    def write(self, data: bytes) -> bool:
        if len(data) > MAX_DATA - self.used:
            return False
        for value in data:
            self.storage[self.write_pos] = value
            self.write_pos = (self.write_pos + 1) % MAX_DATA
        self.used += len(data)
        return True

    def peek(self, count: int) -> bytes:
        if not 0 <= count <= self.used:
            raise BackendFailure("incomplete receive record")
        return bytes(self.storage[(self.read_pos + i) % MAX_DATA] for i in range(count))

    def consume(self, count: int) -> bytes:
        data = self.peek(count)
        self.read_pos = (self.read_pos + count) % MAX_DATA
        self.used -= count
        return data


@dataclass
class Socket:
    protocol: str
    port: int
    resident: bool = False
    remote: bytes = b"\0\0\0\0"
    remote_port: int = 0
    state: int = 2  # TCP SYN-SENT; UDP does not use this field.
    tx: Ring = field(default_factory=Ring)
    rx: Ring = field(default_factory=Ring)


class FakeBackend:
    """Three application handles; the fourth hardware socket is never allocated.

    Counters and peer_events are test observations, not cartridge memory. Reset
    keeps that history so tests can see an action whose response was lost.
    """

    def __init__(self):
        self.sockets: dict[int, Socket] = {}
        self.executions = Counter()
        self.effects = Counter()
        self.peer_events: list[tuple[str, int, bytes]] = []
        self.service_steps = 0
        self.reset_count = 0
        self.fail_next = False
        self.network_up = True

    def reset(self):
        self.sockets.clear()
        self.fail_next = False
        self.reset_count += 1

    def service(self):
        self.service_steps += 1

    def _open(self, protocol, port, resident=False, remote=b"\0" * 4, remote_port=0):
        used = {s.port for s in self.sockets.values() if s.protocol == protocol}
        if port == 65535:
            # Predictable fixture choice in the required ephemeral range, not randomness.
            port = next(p for p in range(16384, 32768) if p not in used)
        if any(s.protocol == protocol and s.port == port and
               (protocol == "udp" or (s.remote, s.remote_port) == (remote, remote_port))
               for s in self.sockets.values()):
            return Call(EXISTS)
        handle = next((h for h in range(1, 4) if h not in self.sockets), None)
        if handle is None:
            return Call(NO_FREE)
        self.sockets[handle] = Socket(protocol, port, resident, remote, remote_port)
        self.effects["open"] += 1
        return Call(OK, b=handle)

    def establish(self, handle):
        self.sockets[handle].state = 4

    def peer_fin(self, handle):
        socket = self.sockets[handle]
        if socket.state == 5:
            del self.sockets[handle]
        else:
            socket.state = 7

    def inject_tcp(self, handle, data):
        return self.sockets[handle].rx.write(data)

    def inject_udp(self, handle, data, ip=b"\xc0\x00\x02\x01", port=1234):
        if len(data) > MAX_UDP:
            return False
        record = ip + port.to_bytes(2, "big") + len(data).to_bytes(2, "big") + data
        return self.sockets[handle].rx.write(record)

    def tcp_send(self, handle, data, flags=0):
        socket = self.sockets.get(handle)
        if socket is None or socket.protocol != "tcp":
            return Call(NO_CONN)
        if flags & ~3:
            return Call(INV_PARAM)
        if not data:
            return Call(OK)
        if socket.state not in (4, 7):
            return Call(CONN_STATE)
        if not socket.tx.write(data):
            return Call(BUFFER)
        self.effects["tcp_send"] += 1
        self.peer_events.append(("tcp", handle, bytes(data)))
        return Call(OK)

    def execute(self, call: Call) -> Call | None:
        self.executions[call.a] += 1
        if self.fail_next:
            self.fail_next = False
            raise BackendFailure("injected chip failure")
        op = call.a
        if op == 8:
            if call.b not in (0, 1) or call.hl == 0 or 65520 <= call.hl <= 65534:
                return Call(INV_PARAM)
            return self._open("udp", call.hl, bool(call.b))
        if op == 13:
            remote = call.aux[:4]
            rport = int.from_bytes(call.aux[4:6], "little")
            lport = int.from_bytes(call.aux[6:8], "little")
            timeout = int.from_bytes(call.aux[8:10], "little")
            flags = call.aux[10]
            valid_timeout = timeout in range(1081) or timeout == 65535
            if flags & 0xF0 or not valid_timeout:
                return Call(INV_PARAM)
            if flags & 5:  # Passive and TLS are outside this model's profile.
                return Call(NOT_IMP)
            if remote == b"\0" * 4 or rport == 0:
                return Call(INV_PARAM)
            if not self.network_up:
                return Call(NO_NETWORK)
            return self._open("tcp", lport, bool(flags & 2), remote, rport)
        if op not in range(9, 19):
            return None
        protocol = "udp" if op <= 12 else "tcp"
        if op in (9, 14, 15) and call.b == 0:
            handles = [h for h, s in self.sockets.items()
                       if s.protocol == protocol and not s.resident]
        else:
            socket = self.sockets.get(call.b)
            if socket is None or socket.protocol != protocol:
                return Call(NO_CONN)
            handles = [call.b]
        if op in (9, 14, 15):
            for handle in handles:
                if op == 14:
                    self.sockets[handle].state = 5  # FIN-WAIT; allocation retained.
                else:
                    del self.sockets[handle]
                self.effects["close" if op != 15 else "abort"] += 1
            return Call(OK)
        socket = self.sockets[call.b]
        if op == 10:
            size = int.from_bytes(socket.rx.peek(8)[6:8], "big") if socket.rx.used else 0
            return Call.make(OK, b=int(bool(socket.rx.used)), hl=socket.port, de=size)
        if op == 11:
            if len(call.data) > MAX_UDP:
                return Call(LARGE_DGRAM)
            if not self.network_up:
                return Call(NO_NETWORK)
            self.effects["udp_send"] += 1
            self.peer_events.append(("udp", call.b, call.data))
            return Call(OK)
        if op == 12:
            if not socket.rx.used:
                return Call(NO_DATA)
            header = socket.rx.peek(8)
            size = int.from_bytes(header[6:8], "big")
            if size > MAX_UDP or size + 8 > socket.rx.used:
                raise BackendFailure("malformed UDP record")
            # Take a complete record even when no payload is copied to the host.
            record = socket.rx.consume(size + 8)
            self.effects["udp_receive"] += 1
            return Call.make(OK, bc=size, l=header[0], h=header[1], e=header[2], d=header[3],
                             ix=int.from_bytes(header[4:6], "big"), data=record[8:8 + call.de])
        if op == 16:
            info = socket.remote + socket.remote_port.to_bytes(2, "little") + socket.port.to_bytes(2, "little")
            return Call.make(OK, b=socket.state, hl=socket.rx.used,
                             ix=MAX_DATA - socket.tx.used, aux=info)
        if op == 17:
            return self.tcp_send(call.b, call.data, call.c)
        if op == 18:
            data = socket.rx.consume(min(call.hl, socket.rx.used))
            self.effects["tcp_receive"] += 1
            return Call.make(OK, bc=len(data), data=data)
        raise AssertionError("unhandled modeled operation")
