'''Handles serial communication and threading.
Exposes clean callbacks to the MainWindow.'''



from PyQt6.QtCore import QObject, QRunnable, QThreadPool, pyqtSignal, QThread, pyqtSlot
from PyQt6.QtSerialPort import QSerialPortInfo

import serial
import queue
import re
import time

from typing import List, Literal, Union



class Worker(QRunnable):
    """Worker thread.

    Inherits from QRunnable to handler worker thread setup, signals and wrap-up.

    :param fn: The function callback to run on this worker thread.
                     Supplied args and kwargs will be passed through to the runner.
    :type fn: function
    :param args: Arguments to pass to the callback function
    :param kwargs: Keywords to pass to the callback function

    Usage example:
        worker = Worker(
            self.execute_this_fn
        )  # Any other args, kwargs are passed to the run function
        # Execute
        self.threadpool.start(worker) # self.threadpool is a QThreadPool instance
    """

    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs

    @pyqtSlot()
    def run(self):
        """Initialise the runner function with passed args, kwargs."""
        self.fn(*self.args, *self.kwargs)


class SerialSignals(QObject):
    '''Signals emitted to the GUI thread.
    
    Each signal is handled by a corresponding MainWindow method.
    '''

    position_updated = pyqtSignal(str, float, float, list)         # "MPos"|"WPos", pos_x, pos_y, new_wco
    status_changed = pyqtSignal(str)                             # "Idle", "Run", "Alarm", etc.
    offset_updated = pyqtSignal(float, float)                   # g54_x, g54_y
    connection_changed = pyqtSignal(bool)                       # True if connected
    error_occurred = pyqtSignal(str)                            # Error message string
    raw_message_received = pyqtSignal(str)                      # Console log feed
    batch_processed = pyqtSignal(bool)



class SerialWorker(QRunnable):

    def __init__(self):
        super().__init__()
        self._serial: serial.Serial | None = None
        self._is_running = True     # flag: helps with clean shutdown

        self._command_queue = queue.Queue()
        self._acks_waiting = 0

        self.signals = SerialSignals()

        # threading
        self._threadpool = QThreadPool()

        # settings
        # applied on startup:
        self.DEFAULT_FEED_RATE = 100        # mm/min
        self.POSITION_QUERYING_INTERVAL = 50     # milliseconds

        # other settings
        self.COMMAND_MAX_WAIT_MS = 2000
        self.ACK_THRESHOLD = 3

        self.COMMAND_QUEUE_POLL_MS = 10     # when command queue is empty
        self.READ_POLL_MS = 50              # for polling fluidnc for outputs

        # to measure response times
        # depends on read cycle, among other things
        self.start = 0
        self.end = 0

        




    # --- Public API (Called by GUI or main thread) ---
    def connect_to(self, port_name: str) -> serial.Serial:
        self._serial = serial.Serial(port_name, 115200, timeout=0.1)

        # Wake up and initialize GRBL
        self._serial.write(b"\r\n\r\n")
        time.sleep(1)
        self._serial.reset_input_buffer()

        # initialize workers
        # both terminate when serial port disconnects
        _command_worker = Worker(self._process_commands)
        self._threadpool.start(_command_worker)
        _reader_thread = Worker(self._read_from_serial)
        self._threadpool.start(_reader_thread)

        # initialize GRBL config
        self.send_command("$X")       # Remove if limit switches work
        self.send_command('$#')   # load existing sample coordinates
        self.send_command('$10=0')   # set query to report work position (WPos)
        self.send_command(f'$Report/Interval={self.POSITION_QUERYING_INTERVAL}')   # set automatic querying `?`
        self.send_command(f'G21 G17 F{self.DEFAULT_FEED_RATE}')   # units in mm, XY plane, speed

        return self._serial


    def disconnect_port(self):
        self.clear_command_queue()
        self._serial.close()


    def list_available_ports(self):
        return QSerialPortInfo.availablePorts()


    def port_open(self):
        return self._serial and self._serial.is_open


    def stop(self):
        '''Call from main window closeEvent.'''
        self._is_running = False

        if self.port_open():
            try:
                # Send GRBL Real-time Soft Reset (0x18 / Ctrl+X)
                # This halts motion immediately and purges GRBL's internal planner buffer
                self._serial.write(b"\x18")

                # Flush PySerial buffers
                self._serial.reset_input_buffer()
                self._serial.reset_output_buffer()
            except (serial.SerialException, OSError) as e:
                print(f"Error resetting buffers: {e}")

            self._serial.close()

        self.clear_command_queue()


    def set_working_coordinate_system(self, x, y):
        '''Sets new WCO for G54.'''

        # set current x, y as (0, 0) of sample coordinate system
        self.send_command(f'G10 L2 P1 X{x} Y{y}')
        self.send_command('G54')

        # reader thread automatically parses the new WCO
        # assuming WCO included in next `?` status report when WCO changes


    def unlock_alarm(self):
        self.send_command("$X")


    def jog(self, axis, change, speed):
        '''Speed is in mm/min, assuming G21 was set.'''
        self.send_command(f"G91\nG1 {axis}{change} F{speed}\nG90")


    def pseudo_home(self, mpos_x, mpos_y, speed):
        '''Intended for *sample* homing.

        Not recommended for homing physical machine, but can be an temporary alternative to limit switches.
        '''
        
        self.send_command(f'G91 G1 X{-mpos_x} F{speed}')
        self.send_command(f'G91 G1 Y{-mpos_y} F{speed}')


    def emergency_stop(self):
        '''Sends Ctrl-X byte and cancels pending commands.
        Puts firmware into an alarm state - must rehome to exit alarm state.
        '''
        self.send_immediate(0x18)
        self.clear_command_queue()


    def send_command(self, command: str):
        '''Queues command for processing.'''

        # split by line
        for line in command.split('\n'):
            line = line.strip()
            if line:
                self._command_queue.put(line)


    def send_batch_commands(self, commands: List[str]):
        '''Use case: Reading g-code file instead of one-off commands.

        Doesn't do much on its own right now.
        Can be modified later to handle batch commands as needed.
        '''

        num = 0
        for c in commands:
            num += len(c.split('\n'))
            self.send_command(c)


    def send_immediate(self, cmd: Union[str, bytes, int]):
        '''Bypasses command queue + all currently running g-code.
        Use for `!` feed hold and other interrupts.

        Note: Do not send `?` status queries, since FluidNC already does this via `$Report/Interval`

        See here for list of real-time control commands: https://github.com/gnea/grbl/blob/master/doc/markdown/interface.md#real-time-control-commands
        '''
        if not self.port_open():
            return

        if isinstance(cmd, str):
            data = cmd.encode("ascii")
        elif isinstance(cmd, int):
            data = bytes([cmd])
        elif isinstance(cmd, (bytes, bytearray)):
            data = bytes(cmd)
        else:
            raise TypeError(f"Unsupported command type: {type(cmd)}")

        self._serial.write(data)
        self._serial.flush()  # Flushes OS write buffer immediately



    # --- Internal Helpers ---

    def _process_commands(self):
        '''Runs in background to process command queue.

        A command is sent to the board if either:
            1. Less than 3 commands awaiting 'ok' or 'error' response
            2. More than command_max_wait_ms milliseconds have passed since last command

        DO NOT RUN FROM MAIN THREAD. Intended to run from a Worker thread.

        Assumes each command is a single non-empty line.'''


        def interruptible_sleep(duration: float, ack_threshold, check_interval: float = 0.05):
            # wake up if less than 3 commands waiting for ack
            start = time.monotonic()
            while time.monotonic() - start < duration:
                if self._acks_waiting < ack_threshold:
                    break
                time.sleep(min(check_interval, duration - (time.monotonic() - start)))


        while self.port_open():
            if self._command_queue.empty():
                time.sleep(self.COMMAND_QUEUE_POLL_MS/1000)
                continue
            
            interruptible_sleep(self.COMMAND_MAX_WAIT_MS, self.ACK_THRESHOLD)

            # send command to serial
            self.start = time.perf_counter()
            command = self._command_queue.get()

            self._serial.write(f"{command}\n".encode('utf-8'))
            
            self._acks_waiting += 1

    
    def _read_from_serial(self):
        
        buffer = b""
        while self.port_open():
            try:
                if not self._serial.in_waiting:
                    # prevent hogging CPU cycles
                    time.sleep(self.READ_POLL_MS/1000)
                else:
                
                    # read whatever is waiting in the serial buffer
                    buffer += self._serial.read(self._serial.in_waiting)

                    # split by newline
                    while b"\n" in buffer:
                        line_bytes, buffer = buffer.split(b"\n", 1)
                        line = line_bytes.decode("utf-8").strip()

                        if not line:
                            continue

                        self._parse_serial_output(line)
                        
            except (OSError, serial.SerialException) as e:
                            # Catch the port closing exception silently since it's an intentional disconnect
                            print("Serial port disconnected or closed.")
                            break
            except Exception as e:
                print(f"Read error: {e}")


    def _parse_serial_output(self, line: str):
        '''Parses serial outputs from GRBL.

        GRBL has **two kinds** of messages:
            1. Response Message: Starts with `ok` or `error`
            2. Push Message: Feedback on what GRBL is doing,
                usually in response to a user query
                or to let the user know something happened.

        Read more here: https://github.com/gnea/grbl/blob/master/doc/markdown/interface.md
        
        Note on reporting WCO:
            Code typically updates WCO when included in the status report (enclosed in chevrons.)
            Because it's most convenient to update WCO alongside the most recently reported position.

            It also updates when the `$#` query responds, but this is less reliable since `$#` does not also
            report the most recent position.

            If there is no WCO in the status report, it uses an empty list as a placeholder.

        '''
        def parse_position_field(line: str) -> tuple[Literal["MPos", "WPos"], list[float]]:
            # Example line: MPos:0.0,0.0
            pos_type, coords_str = line.split(":", 1)
            coords = [float(x) for x in coords_str.split(",")][0:2]

            return pos_type, coords

        def parse_wco_field(line: str):
            # Example line: WCO:5.000,5.000,0.000
            try:
                _, coords_str = line.split(":", 1)
                return [float(x) for x in coords_str.split(",")][0:2]
            except Exception as e:
                print(f'Cannot parse wco field: {line}')
                return []

        RESPONSE_REGEX = re.compile(r"^(ok|error(?::(\d+))?)\b", re.IGNORECASE)
        STATUS_REGEX = re.compile(r"^<([^|>]+)\|(.*)>$")
        WCO_REGEX = re.compile(r"^\[G54:([^\]]+)\]$")

        line = line.strip()

        if status_match := STATUS_REGEX.match(line):
            # Status report contains following info:
            #    1. Status: Idle, Run, etc
            #    2. Position
            #    3. (Sometimes) Work coordinate offset: Usually when new sample home is set

            state, data = status_match.groups()
            fields = data.split("|")

            # update state
            self.signals.status_changed.emit(state)

            # update position
            if pos_field := next((f for f in fields if f.startswith(("MPos:", "WPos:"))), None):
                # If `WPos:` is given, use `MPos = WPos + WCO`.
      		    # If `MPos:` is given, use `WPos = MPos - WCO`.
                
                pos_type, coords = parse_position_field(pos_field)

                # check for wco update
                wco_field = next((f for f in fields if f.startswith("WCO:")), None)
                new_wco = parse_wco_field(wco_field) if wco_field else []

                # send signal
                self.signals.position_updated.emit(pos_type, *coords, new_wco)
                

        elif resp_match := RESPONSE_REGEX.match(line):
            resp: Literal["ok", "error"] = resp_match.group(0)

            if resp == "error":
                # stop all operation
                print("WARNING: Encountered g-code error. Halting movement.")
                self.signals.error_occurred.emit(line)
                self.emergency_stop()

            self.end = time.perf_counter()
            dur = self.end - self.start
            # print(f'response took {dur:.4f} seconds')
            
            self._acks_waiting -= 1

        elif wco_match := WCO_REGEX.match(line):
            # Note: WCO is usually reported alongside `?` status query when G54 updates.
            # Hence, most WCO updates happen when STATUS_REGEX matches.
            # WCO updates are also most useful when sent alongside the most recently reported position.

            # This WCO_REGEX check runs only in response to `$#` queries.

            # work coordinate offsets from `$#` query
            # only first two coordinates extracted: x and y
            coords = [float(v) for v in wco_match.group(1).split(",")][0:2]

            self.signals.offset_updated.emit(*coords)

        else:
            # print(f'GRBL message: {line}')
            pass


    def clear_command_queue(self):

        while not self._command_queue.empty():
            try:
                c = self._command_queue.get_nowait()
                print('remove command: ', c)

                self._command_queue.task_done()
            except (queue.Empty, ValueError) as e:
                print('cannot remove command', e)
                break



