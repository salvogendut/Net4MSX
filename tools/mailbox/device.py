"""Byte-clocked register/FIFO model with bounded logical transport storage.

Each tick performs a bounded scheduler visit. Ticks have no physical duration.
Python object overhead and temporary codec objects are not a firmware RAM map.
"""

from collections import deque
import zlib

from .backend import BackendFailure, FakeBackend
from .codec import (Call, FIFO_DEPTH, FormatError, Frame, Header, HELLO_LIMITS,
                    Kind, MAX_FRAME, validate_request)

STATUS, CONTROL, TX_FREE, RX_COUNT, DATA, VERSION, FAULT, SIGNATURE = range(8)
REWIND, RESET = 1, 128
READY, RX_AVAIL, TX_SPACE, REPLY_HELD, EXECUTING, FAULTED, ACTIVE, CONTROL_BUSY = (
    1, 2, 4, 8, 16, 32, 64, 128
)


class Mailbox:
    def __init__(self, backend=None, *, execution_delay=2, execution_limit=100):
        self.backend = backend if backend is not None else FakeBackend()
        self.execution_delay = execution_delay  # None simulates a stuck operation.
        self.execution_limit = execution_limit
        self.clock = 0
        self.tx = deque()
        self.rx = deque()
        self.request = bytearray(MAX_FRAME)
        self.response = bytearray(MAX_FRAME)
        self.scratch = bytearray(16)
        self.fault = 0
        self._reset()

    def _parser_reset(self):
        self.offset = 0
        self.incoming = None
        self.mode = None
        self.crc = 0
        self.wire_crc = 0
        self.different = False

    def _reset(self):
        self.ready = self.active = self.reply_held = self.executing = False
        self.reset_pending = self.control_busy = True
        self.rewind_pending = False
        self.session = 0
        self.expected = 1
        self.last_ack = None
        self.current = None
        self.request_len = self.response_len = self.cursor = 0
        self.committed = False
        self.fault = 0
        self.tx.clear()
        self.rx.clear()
        self._parser_reset()

    def _fault(self, code):
        if not self.fault:
            self.fault = code

    @property
    def tx_free(self):
        return FIFO_DEPTH - len(self.tx) if self.ready and not self.fault else 0

    @property
    def rx_count(self):
        return len(self.rx) if self.ready and not self.fault else 0

    def read(self, offset):
        if offset == STATUS:
            return (READY * self.ready | RX_AVAIL * bool(self.rx_count) |
                    TX_SPACE * bool(self.tx_free) | REPLY_HELD * self.reply_held |
                    EXECUTING * self.executing | FAULTED * bool(self.fault) |
                    ACTIVE * self.active | CONTROL_BUSY * self.control_busy)
        if offset == TX_FREE:
            return self.tx_free
        if offset == RX_COUNT:
            return self.rx_count
        if offset == VERSION:
            return 1
        if offset == SIGNATURE:
            return 0x4E
        if offset == FAULT:
            return self.fault
        if offset == DATA:
            if not self.ready or self.fault:
                return 255
            if self.control_busy or not self.rx:
                self._fault(1)
                return 255
            return self.rx.popleft()
        return 0

    def write(self, offset, value):
        if not 0 <= value <= 255:
            raise ValueError("register writes are bytes")
        if offset == CONTROL and value == RESET:
            self._reset()  # Priority over boot, fault and rewind.
        elif offset == CONTROL:
            if not self.ready or self.fault:
                return
            if value != REWIND or not self.reply_held or self.control_busy:
                self._fault(5)
            else:
                self.control_busy = self.rewind_pending = True
        elif offset == DATA:
            if not self.ready or self.fault:
                return
            if self.control_busy or not self.tx_free:
                self._fault(1)
            else:
                self.tx.append(value)

    @staticmethod
    def _identity(header):
        return header.session, header.sequence, header.opcode

    def _start_frame(self):
        try:
            header = Header.decode(bytes(self.scratch))
        except FormatError:
            self._fault(2)
            return
        self.incoming = header
        if header.kind == Kind.RESPONSE:
            self._fault(2)
            return
        if header.kind in (Kind.HELLO, Kind.ACK) and header.length:
            self._fault(2)
            return
        if header.kind == Kind.HELLO and (header.sequence or header.opcode != 255):
            self._fault(2)
            return
        if header.kind == Kind.HELLO and not self.session:
            self.mode = "new"
        elif header.session != self.session:
            self._fault(3)
            return
        elif header.kind == Kind.ACK:
            if self.last_ack == self._identity(header):
                self.mode = "old_ack"
            elif (self.reply_held and self.current is not None and
                  self._identity(header) == self._identity(self.current)):
                self.mode = "ack"
            else:
                self._fault(3)
                return
        elif self.request_len:
            if (self.current.sequence != header.sequence or
                    self.current.kind != header.kind):
                self._fault(3)
                return
            self.mode = "duplicate"
            self.different = self.request[:16] != self.scratch
        elif (header.kind == Kind.REQUEST and self.active and
              header.sequence == self.expected):
            self.mode = "new"
        else:
            self._fault(3)
            return
        if self.mode == "new":
            self.request[:16] = self.scratch

    def _accept_byte(self, value):
        index = self.offset
        self.offset += 1
        if index < 16:
            self.scratch[index] = value
            self.crc = zlib.crc32(bytes((value,)), self.crc)
            if self.offset == 16:
                self._start_frame()
            return
        header = self.incoming
        end = 16 + header.length
        if index < end:
            self.crc = zlib.crc32(bytes((value,)), self.crc)
        else:
            self.wire_crc |= value << (8 * (index - end))
        if self.mode == "new":
            self.request[index] = value
        elif self.mode == "duplicate":
            self.different |= index >= self.request_len or self.request[index] != value
        if self.offset == end + 4:
            if self.crc != self.wire_crc:
                self._fault(2)
            else:
                self._finish_frame()
            self._parser_reset()

    def _store_response(self, payload, status=0):
        h = self.current
        wire = Frame.make(Kind.RESPONSE, h.session, h.sequence, h.opcode,
                          payload, status).encode()
        self.response[:len(wire)] = wire
        self.response_len = len(wire)
        self.cursor = 0

    def _finish_frame(self):
        header = self.incoming
        if self.mode == "duplicate":
            if self.different or self.offset != self.request_len:
                self._fault(4)
            return
        if self.mode == "old_ack":
            return
        if self.mode == "ack":
            self.last_ack = self._identity(header)
            self.active = True
            self.expected = header.sequence + 1
            self.request_len = self.response_len = self.cursor = 0
            self.current = None
            self.reply_held = False
            self.rx.clear()  # An early ACK cannot leave stale bytes for the next reply.
            return
        if header.kind == Kind.REQUEST:
            try:
                call = Call.decode(bytes(self.request[16:self.offset - 4]))
                validate_request(header.opcode, call)
            except FormatError:
                self._fault(2)
                return
        self.current = header
        self.request_len = self.offset
        if header.kind == Kind.HELLO:
            self.session = header.session
            self._store_response(HELLO_LIMITS)
            self.reply_held = True
        else:
            self.executing = True
            self.committed = False
            self.started = self.clock

    def tick(self):
        """One service visit: at most one input and one output FIFO byte."""
        self.clock += 1
        if self.reset_pending:
            self.backend.reset()
            self.reset_pending = self.control_busy = False
            self.ready = True
            return
        if self.fault:
            return
        self.backend.service()
        if self.rewind_pending:
            self.rx.clear()
            self.cursor = 0
            self.rewind_pending = self.control_busy = False
            return
        if self.executing:
            elapsed = self.clock - self.started
            if elapsed >= self.execution_limit:
                self._fault(6)
                return
            if self.committed:
                self.executing = False
                self.reply_held = True
            elif self.execution_delay is not None and elapsed >= self.execution_delay:
                try:
                    call = Call.decode(bytes(self.request[16:self.request_len - 4]))
                    result = self.backend.execute(call)
                    self._store_response(result.encode() if result is not None else b"",
                                         0 if result is not None else 1)
                except BackendFailure:
                    self._fault(6)
                    return
                self.committed = True
                # Publication is a separate visit, so reset can interrupt after effects.
        if self.tx:
            self._accept_byte(self.tx.popleft())
        if not self.fault and self.reply_held and len(self.rx) < FIFO_DEPTH and self.cursor < self.response_len:
            self.rx.append(self.response[self.cursor])
            self.cursor += 1
        self.assert_bounds()

    def assert_bounds(self):
        assert len(self.tx) <= FIFO_DEPTH and len(self.rx) <= FIFO_DEPTH
        assert len(self.request) == len(self.response) == MAX_FRAME
        assert len(self.scratch) == 16
        assert 0 <= self.offset <= MAX_FRAME
        assert 0 <= self.request_len <= MAX_FRAME
        assert 0 <= self.cursor <= self.response_len <= MAX_FRAME
        for socket in self.backend.sockets.values():
            for ring in (socket.tx, socket.rx):
                assert len(ring.storage) == 2048 and 0 <= ring.used <= 2048
