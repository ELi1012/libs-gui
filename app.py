'''GUI to control stage movement of LIBS soil analyzer.

Implemented using PyQt6.

Features:
- Set width/height of sample and gantry (physical frame)
- Manual controls to jog the stage
- Scan options: Set resolution of scan


Misc notes:
- sending $# will only update the coordinate offsets if the reader loop is active


'''


import sys
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, 
                             QPushButton, QLineEdit, QLabel, QGridLayout,
                             QFrame, QComboBox)
from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtSerialPort import QSerialPortInfo
import serial
import re
import threading
import time
import re

from raster import generate_raster_commands





class ConfigCard(QFrame):
    """A reusable card component for logical grouping of config settings."""
    def __init__(self, title, border_color="black"):
        super().__init__()
        
        self.setStyleSheet(f"""
            QFrame {{
                border: 2px solid {border_color};
                border-radius: 8px;
            }}
            QLabel {{
                border: none;
                font-family: Arial;
                font-size: 14px;
            }}
        """)
        
        card_layout = QVBoxLayout(self)
        self.card_layout = card_layout
        card_layout.setContentsMargins(10, 5, 10, 10)
        card_layout.setSpacing(5)
        
        # Header text
        header = QLabel(title)
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header.setStyleSheet("font-weight: bold;")
        card_layout.addWidget(header)
        
        # Separator Line
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Plain)
        line.setStyleSheet(f"border: 1px solid {border_color}; margin-bottom: 5px;")
        card_layout.addWidget(line)
    
    def addLayoutToCard(self, layout):
        '''better than needing to know `card_layout` belongs to the object'''
        self.card_layout.addLayout(layout)
        


class StageSizeConfig(QWidget):
    '''Sample + Gantry size config options'''
    def __init__(self):
        super().__init__()

        GANTRY_WIDTH_DEFAULT = 42
        GANTRY_HEIGHT_DEFAULT = 56

        self.config_layout = QHBoxLayout()


        # Sample
        # to access via StageSizeConfig
        self.sample = {
            'width_input': None,
            'height_input': None
        }

        self.sample_frame = ConfigCard('Sample Size')
        self.config_layout.addWidget(self.sample_frame)
        sample_layout = QGridLayout()
        # sample_layout.setSpacing(8)

        sample_layout.addWidget(QLabel("Width (cm):"), 0, 0)
        s_winput = QLineEdit()
        sample_layout.addWidget(s_winput, 0, 1)
        self.sample['width_input'] = s_winput

        sample_layout.addWidget(QLabel("Height (cm):"), 1, 0)
        s_hinput = QLineEdit()
        sample_layout.addWidget(s_hinput, 1, 1)
        self.sample_frame.addLayoutToCard(sample_layout)
        self.sample['height_input'] = s_hinput
        

        # Gantry
        self.gantry = {
            'width_input': None,
            'height_input': None
        }

        self.gantry_frame = ConfigCard('Gantry Size')
        self.config_layout.addWidget(self.gantry_frame)
        gantry_layout = QGridLayout()
        gantry_layout.setSpacing(8)
        
        gantry_layout.addWidget(QLabel("Width (cm):"), 0, 0)
        g_winput = QLineEdit()
        g_winput.setText(str(GANTRY_WIDTH_DEFAULT))
        gantry_layout.addWidget(g_winput, 0, 1)
        self.gantry['width_input'] = g_winput

        gantry_layout.addWidget(QLabel("Height (cm):"), 1, 0)
        g_hinput = QLineEdit()
        g_hinput.setText(str(GANTRY_HEIGHT_DEFAULT))
        gantry_layout.addWidget(g_hinput, 1, 1)
        self.gantry_frame.addLayoutToCard(gantry_layout)
        self.gantry['height_input'] = g_hinput

        self.setLayout(self.config_layout)


    
    def init_listeners(self, fn_swidth, fn_sheight, fn_gwidth, fn_gheight):
        '''Connects functions to trigger after input change.

        Purpose: Display inputs via some parent widget (eg. visual stages)

        fn_x can be lambda functions: lambda args: expression

        Usage Example:
            # labels (parent)
            swtext = QLabel(sample_width)
            shtext = QLabel(sample_height)
            gwtext = QLabel(gantry_width)
            ghtext = QLabel(gantry_height)

            # connect to parent labels
            stages_config.init_listeners(
                lambda newText: swtext.setText(newText),
                lambda newText: shtext.setText(newText),
                lambda newText: gwtext.setText(newText),
                lambda newText: ghtext.setText(newText),
            )
        '''

        self.sample['width_input'].textChanged.connect(fn_swidth)
        self.sample['height_input'].textChanged.connect(fn_sheight)
        self.gantry['width_input'].textChanged.connect(fn_gwidth)
        self.gantry['height_input'].textChanged.connect(fn_gheight)

    
    # returns the widgets themselves
    def get_sample_width(self):
        return self.sample['width_input'].text()
    
    def get_sample_height(self):
        return self.sample['height_input'].text()
    
    def get_gantry_width(self):
        return self.gantry['width_input'].text()
    
    def get_gantry_height(self):
        return self.gantry['height_input'].text()
    

    # sanity checker
    
    def sample_dimensions_valid(self):
        width = self.sample['width_input'].text().strip()
        height = self.sample['height_input'].text().strip()
        return self.dimensions_valid(width, height)
    
    def gantry_dimensions_valid(self):
        width = self.gantry['width_input'].text().strip()
        height = self.gantry['height_input'].text().strip()
        return self.dimensions_valid(width, height)

    def dimensions_valid(self, width, height):

        # empty?
        if not width or not height:
            return False
        
        # is int?
        try:
            int(width)
            int(height)
        except ValueError:
            return False
        
        return True
    


    



class SizeCard(QFrame):
    """A reusable card component with a header line and grid form inputs."""
    def __init__(self, title, border_color="black"):
        super().__init__()
        
        # Style the card with rounded corners and custom border color
        self.setStyleSheet(f"""
            QFrame {{
                border: 2px solid {border_color};
                border-radius: 8px;
            }}
            QLabel {{
                border: none;
                font-family: Arial;
                font-size: 14px;
            }}
            QLineEdit {{
                border: 1px solid #ccc;
                border-radius: 4px;
                padding: 2px;
            }}
        """)
        
        card_layout = QVBoxLayout(self)
        card_layout.setContentsMargins(10, 5, 10, 10)
        card_layout.setSpacing(5)
        
        # Header text
        header = QLabel(title)
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header.setStyleSheet("font-weight: bold;")
        card_layout.addWidget(header)
        
        # Separator Line
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Plain)
        line.setStyleSheet(f"border: 1px solid {border_color}; margin-bottom: 5px;")
        card_layout.addWidget(line)
        
        # Form grid (Width / Height inputs)
        form_layout = QGridLayout()
        form_layout.setSpacing(8)
        
        form_layout.addWidget(QLabel("Width (cm):"), 0, 0)
        self.width_input = QLineEdit()
        form_layout.addWidget(self.width_input, 0, 1)
        
        form_layout.addWidget(QLabel("Height (cm):"), 1, 0)
        self.height_input = QLineEdit()
        form_layout.addWidget(self.height_input, 1, 1)
        
        card_layout.addLayout(form_layout)
    
    




class CoreXYController(QWidget):
    def __init__(self):
        super().__init__()
        self.serial_port = None

        # --- Internal Coordinate Tracking ---
        self.current_wpos_x = 0.0  # Used for Sample Boundary checking
        self.current_wpos_y = 0.0

        self.current_mpos_x = 0.0  # Used for physical machine tracking
        self.current_mpos_y = 0.0
        

        # Reference Point (Sample Location)
        self.sample_x = None
        self.sample_y = None
        self.sample_coordinate_offset = (0, 0)      # update when connecting

        # send-line protocol
        self.command_semaphore = threading.Semaphore(1) # Allows 1 command at a time
        self.STATUS_REGEX = re.compile(r'<(.*?)>')
        
        # default feed rate
        self.DEFAULT_FEED_RATE = 800        # mm/min
        # TODO: set feed rate on serial connection

        # how often to update position
        self.MOTION_REPORTING_INTERVAL = 50     # milliseconds


        self.initUI()
        
    def initUI(self):
        self.setWindowTitle('FluidNC / GRBL CoreXY Controller')
        main_layout = QVBoxLayout()


        # --- Connection Row
        conn_layout = QHBoxLayout()
        self.port_combo = QComboBox() 
        # self.port_input = QLineEdit('/dev/cu.usbmodem101') 
        self.btn_refresh = QPushButton("Refresh")
        self.btn_connect = QPushButton('Connect')
        self.btn_connect.clicked.connect(self.toggle_connection)
        conn_layout.addWidget(QLabel('Port:'))
        conn_layout.addWidget(self.port_combo)
        conn_layout.addWidget(self.btn_refresh)
        conn_layout.addWidget(self.btn_connect)
        main_layout.addLayout(conn_layout)

        self.btn_refresh.clicked.connect(self.populate_ports)


        # --- Stage Sizes (Sample and Gantry)
        stages_config = StageSizeConfig()
        self.stages_config = stages_config


        main_layout.addWidget(stages_config)

        sample_width = stages_config.get_sample_width()
        sample_height = stages_config.get_sample_height()
        gantry_width = stages_config.get_gantry_width()
        gantry_height = stages_config.get_gantry_height()

        # TEMP: display sample/gantry dimensions
        # replace with graphic

        dimensions_layout = QGridLayout()
        swtext = QLabel(sample_width)
        shtext = QLabel(sample_height)
        gwtext = QLabel(gantry_width)
        ghtext = QLabel(gantry_height)
        dimensions_layout.addWidget(swtext, 0, 0)
        dimensions_layout.addWidget(shtext, 0, 1)
        dimensions_layout.addWidget(gwtext, 1, 0)
        dimensions_layout.addWidget(ghtext, 1, 1)
        main_layout.addLayout(dimensions_layout)
        stages_config.init_listeners(
            lambda newText: swtext.setText(newText),
            lambda newText: shtext.setText(newText),
            lambda newText: gwtext.setText(newText),
            lambda newText: ghtext.setText(newText),
        )
        

        

        # --- Manual Controls
        manual_controls_config = ConfigCard("Manual Controls")

        manual_controls_layout = QVBoxLayout()

        # step size
        step_size_layout = QHBoxLayout()
        step_size_layout.addWidget(QLabel('Step Size:'))
        self.jog_step_size = QLineEdit('2')
        step_size_layout.addWidget(self.jog_step_size)
        manual_controls_layout.addLayout(step_size_layout)

        # arrow controls
        grid_layout = QGridLayout()
        
        self.btn_up = QPushButton('▲ Up (+Y)')
        self.btn_down = QPushButton('▼ Down (-Y)')
        self.btn_left = QPushButton('◀ Left (-X)')
        self.btn_right = QPushButton('▶ Right (+X)')
        self.btn_home = QPushButton('Home ($H)')

        # Arrange in a classic keypad layout
        grid_layout.addWidget(self.btn_up, 0, 1)
        grid_layout.addWidget(self.btn_left, 1, 0)
        grid_layout.addWidget(self.btn_home, 1, 1)
        grid_layout.addWidget(self.btn_right, 1, 2)
        grid_layout.addWidget(self.btn_down, 2, 1)

        manual_controls_layout.addLayout(grid_layout)


        # footer
        manual_footer_layout = QHBoxLayout()
        manual_footer_layout.setSpacing(10)
        sample_gantry_toggle = QPushButton("Sample/Gantry") # TODO: conditional text
        set_ref_btn = QPushButton("Set Ref. Point")
        set_ref_btn.clicked.connect(self.set_new_reference_point)

        manual_footer_layout.addWidget(sample_gantry_toggle)
        manual_footer_layout.addWidget(set_ref_btn)

        manual_controls_layout.addLayout(manual_footer_layout)

        # finish manual controls setup
        manual_controls_config.addLayoutToCard(manual_controls_layout)
        main_layout.addWidget(manual_controls_config)



        # --- Scan Options

        scanning_config = ConfigCard("Scan Options")
        scanning_layout = QVBoxLayout()

        res_layout = QHBoxLayout()
        res_layout.addWidget(QLabel("Scan Resolution (mm)"))
        self.scan_resolution = QLineEdit('1')
        res_layout.addWidget(self.scan_resolution)
        scanning_layout.addLayout(res_layout)

        scanning_config.addLayoutToCard(scanning_layout)
        main_layout.addWidget(scanning_config)



        main_controls_layout = QHBoxLayout()
        main_layout.addLayout(main_controls_layout)


        # Connect UI signals
        self.btn_home.clicked.connect(lambda: self.send_gcode('$H'))
        self.btn_up.clicked.connect(lambda: self.jog(axis='Y', direction=1))
        self.btn_down.clicked.connect(lambda: self.jog(axis='Y', direction=-1))
        self.btn_left.clicked.connect(lambda: self.jog(axis='X', direction=-1))
        self.btn_right.clicked.connect(lambda: self.jog(axis='X', direction=1))


        # Real-time Position Readout Labels for safety awareness
        self.lbl_pos = QLabel("Current Machine Position: X: 0.00, Y: 0.00")
        scanning_layout.addWidget(self.lbl_pos)


        # --- RASTER BUTTON ---

        self.btn_raster = QPushButton('START SCAN')
        self.btn_raster.clicked.connect(self.start_scan)
        main_layout.addWidget(self.btn_raster)

        # finish setup
        self.setLayout(main_layout)


    def set_new_reference_point(self):
        stages_config = self.stages_config

        # exit if sample width and height not set
        if not stages_config.sample_dimensions_valid() or not stages_config.gantry_dimensions_valid():
            print("Sample and gantry config inputs must be an integer value.")
            return

        # exit if reference point exceeds stage bounds
        sample_width = int(stages_config.get_sample_width())
        sample_height = int(stages_config.get_sample_height())
        gantry_width = int(stages_config.get_gantry_width())
        gantry_height = int(stages_config.get_gantry_height())

        xbound = gantry_width - sample_width
        ybound = gantry_height - sample_height

        current_x = self.current_mpos_x
        current_y = self.current_mpos_y

        if current_x > xbound or current_y > ybound:
            print("Reference point cannot exceed stage bounds.")
            return


        # set sample x/y to current machine position
        # machine position == absolute coordinate system
        self.sample_x = current_x
        self.sample_y = current_y

        # tell GRBL the new working position
        self._set_sample_coordinate_system(abs_x=current_x, abs_y=current_y)
        # time.sleep(1)       # avoid sending commands until this is done


    def _set_sample_coordinate_system(self, abs_x: int, abs_y: int):
        ''''''
        # set current location as (0, 0) of sample coordinate system
        self.send_gcode(f'G10 L2 P1 X{abs_x} Y{abs_y}')
        self.send_gcode('G54')      # set G54 as current coordinate system
        
        # reader thread will automatically parse the output coordinate systems (G54)
        self.send_gcode('$#')


    def start_scan(self):
        
        if not self.stages_config.sample_dimensions_valid():
            print("Cannot start scan without valid sample dimensions.")
            return
        
        if not self.scan_resolution.text().strip():
            print("Cannot start scan without resolution input.")
        
        sampleWidth = int(self.stages_config.get_sample_width())
        sampleHeight = int(self.stages_config.get_sample_height())
        resolution = int(self.scan_resolution.text().strip())


        commands = generate_raster_commands(sampleWidth, sampleHeight, resolution, 1000).split('\n')
        for command in commands:
            self.send_gcode(command)


    def jog(self, axis, direction):
        '''Enforces sample size limits on move attempts.'''

        # limits only apply to gantry, not sample
        try:
            distance = float(self.jog_step_size.text())
            limit_x = float(self.stages_config.get_gantry_width())
            limit_y = float(self.stages_config.get_gantry_height())
        except ValueError:
            print("Invalid numerical values in input fields")
            return
        
        # --- PRE-FLIGHT BOUNDARY CHECK ---
        change = distance * direction
        
        # Calculate target position strictly relative to the Sample Origin (WPos)
        target_mpos_x = self.current_mpos_x + (change if axis == 'X' else 0)
        target_mpos_y = self.current_mpos_y + (change if axis == 'Y' else 0)
        
        # Gatekeeper check using explicit Work Position coordinates
        if not (0 <= target_mpos_x <= limit_x and 0 <= target_mpos_y <= limit_y):
            print(f"⚠️ MOVE BLOCKED! Target position ({target_mpos_x:.2f}, {target_mpos_y:.2f}) exceeds gantry limits.")
            return 
        
        gcode = f"G91\nG1 {axis}{change} F3000\nG90"
        self.send_gcode(gcode)


    def populate_ports(self):
        """Scans for available serial ports and populates the dropdown."""
        self.port_combo.clear()
        
        ports = QSerialPortInfo.availablePorts()
        
        if not ports:
            self.port_combo.addItem("No ports found", None)
            return

        for port in ports:
            # Display format: "COM3 - CP2102 USB to UART Bridge" or "/dev/ttyUSB0"
            display_name = f"{port.portName()} ({port.description()})" if port.description() else port.portName()
            
            # Store the system port identifier (e.g., "COM3" or "/dev/ttyUSB0") as itemData
            self.port_combo.addItem(display_name, port.systemLocation())


    def get_selected_port(self):
        """Returns the actual system device name to pass to your serial handler."""
        return self.port_combo.currentData()
    
    def onConnect(self):
        # Start polling GRBL for status updates every 100ms
        self.reader_thread = threading.Thread(target=self.read_from_device, daemon=True)
        self.reader_thread.start()
        
        # Wake up and initialize GRBL
        self.serial_port.write(b"\r\n\r\n")
        time.sleep(2)
        self.serial_port.reset_input_buffer()

        self.send_gcode('$#')   # load existing sample coordinates
        self.send_gcode('$10=0')   # set query to return work position (WPos)
        self.send_gcode(f'$Report/Interval={self.MOTION_REPORTING_INTERVAL}')   # set automatic querying
    

    def toggle_connection(self):
        if self.serial_port is None or not self.serial_port.is_open:
            try:
                print(self.get_selected_port())
                self.serial_port = serial.Serial(self.get_selected_port(), 115200, timeout=0.1)
                self.btn_connect.setText('Disconnect')

                self.onConnect()


            except Exception as e:
                print(f"Connection Error: {e}")
        else:
            # close reader threaad
            self.reader_thread.join(timeout=1)

            print('close serial port')
            self.serial_port.close()
            self.btn_connect.setText('Connect')

    def send_gcode(self, command):
        if self.serial_port and self.serial_port.is_open:
            threading.Thread(target=self._background_send, args=(command,), daemon=True).start()
    
    def _background_send(self, command):
        '''Background thread allows semaphore acquisition without blocking main thread.'''
        for line in command.split('\n'):
            line = line.strip()
            if line:
                self.command_semaphore.acquire()
                self.serial_port.write(f"{line}\n".encode('utf-8'))


    def parse_fluidnc_line(self, text):
        """
        Parses the regular expression coordinates from GRBL/FluidNC status strings.
        Distinguishes between absolute (MPos) and Relative (WPos) coordinates.
        """

        wco_x, wco_y = self.sample_coordinate_offset

        wpos_match = re.search(r'WPos:(-?\d+\.\d+),(-?\d+\.\d+),(-?\d+\.\d+)', text)

        if not wpos_match:
            print('!!! Work position not being reported in status query `?` !!!\nUpdate configuration to report Work Position.')
            return
        
        # extract work position coordinates
        self.current_wpos_x = float(wpos_match.group(1))
        self.current_wpos_y = float(wpos_match.group(2))
        
        # calculate abs position using offset
        self.current_mpos_x = self.current_wpos_x + wco_x
        self.current_mpos_y = self.current_wpos_y + wco_y

        # 4. Update the GUI readout label cleanly showing both systems
        self.lbl_pos.setText(
            f"Absolute (MPos) -> X: {self.current_mpos_x:.2f}, Y: {self.current_mpos_y:.2f}\n"
            f"Sample   (WPos) -> X: {self.current_wpos_x:.2f}, Y: {self.current_wpos_y:.2f}"
        )



    def read_from_device(self):
        buffer = b""
        while self.serial_port and self.serial_port.is_open:
            try:

                if not self.serial_port or not self.serial_port.is_open:
                    break       # port disconnected
                
                if not self.serial_port.in_waiting:
                    # prevent hogging CPU cycles
                    time.sleep(0.01)
                else:
                
                    # read whatever is waiting in the serial buffer
                    buffer += self.serial_port.read(self.serial_port.in_waiting)

                    # split by newline
                    while b"\n" in buffer:
                        line_bytes, buffer = buffer.split(b"\n", 1)
                        line = line_bytes.decode("utf-8").strip()

                        if not line:
                            continue

                        # check if status report interrupt is there
                        status_match = self.STATUS_REGEX.search(line)
                        if status_match:
                            status_line = f"<{status_match.group(1)}>"
                            self.parse_fluidnc_line(status_line)
                            
                            # Remove the status block from the line so we can parse what's left
                            line = self.STATUS_REGEX.sub('', line).strip()

                        # sort status reports
                        if not line:
                            continue

                        if line == 'ok' or line.startswith('error:'):  # comment out this line if arduino not connected
                            self.command_semaphore.release()   # allow next command to execute
                        if line.startswith('[G54:') and line.endswith(']'):
                            # Match G54 followed by 3 comma-separated decimal/negative numbers
                            match = re.match(r'^\[G54:(-?\d+\.?\d*),(-?\d+\.?\d*),(-?\d+\.?\d*)\]$', line)
                            if match:
                                x_co_offset = float(match.group(1))
                                y_co_offset = float(match.group(2))
                                
                                print(f'update coordinate offset: {x_co_offset}, {y_co_offset}')
                                self.sample_coordinate_offset = (x_co_offset, y_co_offset)
                        else:
                            print(f"Controller: {line}")

            except (OSError, serial.SerialException) as e:
                # Catch the port closing exception silently since it's an intentional disconnect
                print("Serial port disconnected or closed.")
                break
            except Exception as e:
                print(f"Read error: {e}")

if __name__ == '__main__':
    app = QApplication(sys.argv)
    ex = CoreXYController()
    ex.show()
    sys.exit(app.exec())