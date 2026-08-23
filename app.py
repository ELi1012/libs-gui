'''GUI to control stage movement of LIBS soil analyzer.

Implemented using PyQt6.

Features:
- Manual controls to jog the stage
- Scan options: Set resolution/speed of scan
- Set width/height of sample and gantry (physical frame)
- Set sample dimensions by jogging stage to sample corners


'''


from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, 
                             QPushButton, QLineEdit, QLabel, QGridLayout,
                             QFrame, QComboBox)
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

import sys
import re
from typing import Literal

from raster import generate_raster_commands
from sample import Point, SpanEndpoints
from hardware.serial_driver import SerialWorker


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

        # manual width/height input
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

    def setWidth(self, newWidth):
        self.sample['width_input'].setText(newWidth)

    def setHeight(self, newHeight):
        self.sample['height_input'].setText(newHeight)


    
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
        
        # is number?
        try:
            float(width)
            float(height)
        except ValueError:
            return False
        
        return True



class CoreXYController(QWidget):
    def __init__(self):
        super().__init__()
        self.serial_port = None


        # --- Settings ---
        self.JOG_SPEED = 500                # mm/min
        self.SAMPLE_HOMING_SPEED = 300      # mm/min
        self.PHYSICAL_HOMING_SPEED = 200    # mm/min

        self.MAX_STAGE_SPEED = 20       # mm/min
        self.MIN_STAGE_SPEED = 1        # mm/min


        # --- Internal Coordinate Tracking ---
        self.current_wpos_x = 0.0  # Used for Sample Boundary checking
        self.current_wpos_y = 0.0

        self.current_mpos_x = 0.0  # Used for physical machine tracking
        self.current_mpos_y = 0.0

        self.isMoving = False

        # Reference Point (Sample Location)
        self.sample_x = None
        self.sample_y = None
        self.sample_coordinate_offset = (0, 0)      # update when connecting
        self.sample_endpoints = SpanEndpoints(
            Point(None, None),
            Point(None, None)
        )

        # send-line protocol
        self.STATUS_REGEX = re.compile(r'<(.*?)>')
        

        # connect serial events
        self.serial = SerialWorker()
        self.serial.signals.position_updated.connect(self.updatePosition)
        self.serial.signals.offset_updated.connect(self.updateWorkCoordinateOffset)
        self.serial.signals.status_changed.connect(self.updateStatus)
        self.serial.signals.batch_processed.connect(self.handleRasterFinished)

        # Valid states types:  `Idle, Run, Hold, Jog, Alarm, Door, Check, Home, Sleep`
        self.status = ""
        self.NOT_MOVING_STATUSES = ["Idle", "Hold", "Alarm"]

        self.initUI()
        
    def initUI(self):
        self.setWindowTitle('LIBS Portable Stage Controller')
        
        main_layout = QVBoxLayout()


        # --- Connection Row
        conn_layout = QHBoxLayout()

        port_lbl_layout = QHBoxLayout() # combo box + label
        self.port_combo = QComboBox() 
        self.btn_refresh = QPushButton("Refresh")
        self.btn_connect = QPushButton('Connect')
        self.btn_connect.clicked.connect(self.toggle_connection)
        self.btn_connect.setEnabled(False)
        self.port_combo.currentIndexChanged.connect(lambda: self.btn_connect.setEnabled(True))
        port_lbl_layout.addWidget(QLabel('Port:'), 1)
        port_lbl_layout.addWidget(self.port_combo, 3)

        conn_layout.addLayout(port_lbl_layout, 3)
        conn_layout.addWidget(self.btn_refresh, 1)
        conn_layout.addWidget(self.btn_connect, 1)
        main_layout.addLayout(conn_layout)

        self.btn_refresh.clicked.connect(self.populate_ports)


        # --- Hardware Controls Container (Disabled by default) ---
        self.controls_container = QWidget()
        self.controls_container.setEnabled(True)
        # self.controls_container.setEnabled(False)
        
        # Internal layout for all hardware controls
        controls_layout = QGridLayout(self.controls_container)
        controls_layout.setSpacing(16)


        # ----- DIMENSIONS CONTROL -----
        # For configuring machine + sample dimensions.


        # --- Stage Sizes (Sample and Gantry)
        stages_config = StageSizeConfig()
        self.stages_config = stages_config

        controls_layout.addWidget(stages_config, 0, 0)

        # Set sample dimensions via jogging
        smeasure_config = ConfigCard("Measure Sample Manually")
        smeasure_layout = QGridLayout()
        smeasure_layout.setSpacing(8)

        self.smeasure_toggle_btn = QPushButton("Begin Measuring Sample Dim.")
        self.smeasure_c1_btn = QPushButton("Corner 1")
        self.smeasure_c2_btn = QPushButton("Corner 2")

        # buttons logic
        self.smeasure_c1_btn.setEnabled(False)
        self.smeasure_c2_btn.setEnabled(False)
        self.smeasure_toggle_btn.clicked.connect(self.toggle_manual_measurement)
        self.smeasure_toggle_btn.setCheckable(True)

        self.temp_corner1 = None
        self.temp_corner2 = None

        self.smeasure_start_label = QLabel("Corner 1: --")
        self.smeasure_end_label = QLabel("Corner 2: --")

        smeasure_layout.addWidget(self.smeasure_toggle_btn, 0, 0, 1, 2)
        smeasure_layout.addWidget(self.smeasure_c1_btn, 1, 0)
        smeasure_layout.addWidget(self.smeasure_start_label, 2, 0)
        smeasure_layout.addWidget(self.smeasure_c2_btn, 1, 1)
        smeasure_layout.addWidget(self.smeasure_end_label, 2, 1)



        # sample measuring logic
        self.smeasure_c1_btn.clicked.connect(
            lambda _checked: self.set_sample_corner('corner1')
        )

        self.smeasure_c2_btn.clicked.connect(
            lambda _checked: self.set_sample_corner('corner2')
        )

        smeasure_config.addLayoutToCard(smeasure_layout)
        controls_layout.addWidget(smeasure_config, 0, 1)
        


        # --- MANUAL CONTROLS ---
        jogging_config = ConfigCard("Manual Controls")

        jogging_layout = QHBoxLayout()
        jogging_layout.setSpacing(16)
        jog_rightside_layout = QVBoxLayout()
        jog_rightside_layout.setSpacing(16)


        jog_leftside_layout = QVBoxLayout()


        # arrow controls
        keypad_widget = QWidget()       # widget to set max width
        keypad_widget.setMaximumWidth(400)  
        keypad_layout = QGridLayout(keypad_widget)
        keypad_layout.setSpacing(8)

        self.btn_up = QPushButton('▲ Up')
        self.btn_down = QPushButton('▼ Down')
        self.btn_left = QPushButton('◀ Left')
        self.btn_right = QPushButton('▶ Right')
        # self.btn_home = QPushButton('Home')

        # Arrange in a classic keypad layout
        keypad_layout.addWidget(self.btn_up, 0, 1)
        keypad_layout.addWidget(self.btn_left, 1, 0)
        # keypad_layout.addWidget(self.btn_home, 1, 1)
        keypad_layout.addWidget(self.btn_right, 1, 2)
        keypad_layout.addWidget(self.btn_down, 2, 1)

        

        # Connect UI signals
        # self.btn_home.clicked.connect(lambda: self.go_to_part_zero())
        self.btn_up.clicked.connect(lambda: self.jog(axis='Y', direction=1))
        self.btn_down.clicked.connect(lambda: self.jog(axis='Y', direction=-1))
        self.btn_left.clicked.connect(lambda: self.jog(axis='X', direction=-1))
        self.btn_right.clicked.connect(lambda: self.jog(axis='X', direction=1))

        jog_leftside_layout.addWidget(keypad_widget)

        # step size input
        step_size_layout = QHBoxLayout()
        step_size_layout.addWidget(QLabel('Step Size:'))
        self.jog_step_size = QLineEdit('2')
        step_size_layout.addWidget(self.jog_step_size)
        jog_leftside_layout.addLayout(step_size_layout)

        # - Set and Return to Reference Point
        ref_point_layout = QHBoxLayout()

        # set new sample home
        set_ref_btn = QPushButton("Set Ref. Point")
        set_ref_btn.clicked.connect(self.set_new_reference_point)
        ref_point_layout.addWidget(set_ref_btn)

        # return to sample home
        self.return_ref_btn = QPushButton("Return to Ref. Point")
        self.return_ref_btn.clicked.connect(self.go_to_part_zero)
        ref_point_layout.addWidget(self.return_ref_btn)

        jog_leftside_layout.addLayout(ref_point_layout)


        # -- right side of manual controls

        # sample/gantry homing toggle
        homing_btn = QPushButton("Home Machine")
        homing_btn.setStyleSheet("background-color: #4CAF50; color: white;")
        homing_btn.clicked.connect(lambda: self.serial.send_command("$H"))
        jog_rightside_layout.addWidget(homing_btn)


        estop_btn = QPushButton("Emergency Stop")
        estop_btn.setStyleSheet("background-color: #DC143C; color: white;")
        estop_btn.clicked.connect(lambda: self.serial.emergency_stop())
        jog_rightside_layout.addWidget(estop_btn)


        
        # jog_rightside_layout.addWidget(set_ref_btn)


        # add right and left side layout
        jogging_layout.addLayout(jog_leftside_layout)
        jogging_layout.addLayout(jog_rightside_layout)

        # finish manual controls setup
        jogging_config.addLayoutToCard(jogging_layout)
        controls_layout.addWidget(jogging_config, 1, 0)


        # --- Scan Options ---

        scanning_config = ConfigCard("Scan Options")
        scanning_layout = QVBoxLayout()

        # resolution
        res_layout = QHBoxLayout()
        res_layout.addWidget(QLabel("Scan Resolution (mm)"))
        self.scan_resolution = QLineEdit('1')
        res_layout.addWidget(self.scan_resolution)
        scanning_layout.addLayout(res_layout)

        # speed
        spd_layout = QHBoxLayout()
        spd_layout.addWidget(QLabel("Speed (mm/s)"))
        self.scan_speed = QLineEdit('20')
        spd_layout.addWidget(self.scan_speed)
        scanning_layout.addLayout(spd_layout)

        scanning_config.addLayoutToCard(scanning_layout)
        controls_layout.addWidget(scanning_config, 1, 1)


        # Real-time Position Readout Labels for safety awareness
        self.lbl_pos = QLabel("Current Machine Position: Unknown")
        scanning_layout.addWidget(self.lbl_pos)


        # --- RASTER BUTTON ---

        self.raster_layout = QHBoxLayout()
        self.raster_layout.setContentsMargins(0, 20, 0, 0)
        self.btn_raster = QPushButton('START SCAN')
        self.btn_raster.setStyleSheet("""
            QPushButton {
                font-size: 18px;
                font-weight: bold;

                background-color: #4CAF50; 
                color: white;
            }
        """)
        self.btn_raster.clicked.connect(self.start_scan)
        self.raster_layout.addWidget(self.btn_raster)

        self.toggle_movement_btn = QPushButton('Stop')
        self.toggle_movement_btn.setCheckable(True)
        self.toggle_movement_btn.setChecked(False)
        self.toggle_movement_btn.clicked.connect(lambda _checked: self.handleToggleMovement(_checked))

        self.raster_layout.addWidget(self.toggle_movement_btn)

        # # unlock button (temporary)
        # self.btn_unlock = QPushButton('Unlock Alarm')
        # self.btn_unlock.clicked.connect(lambda: self.serial.unlock_alarm())
        # controls_layout.addWidget(self.btn_unlock, 2, 1)

        controls_layout.addLayout(self.raster_layout, 2, 0, 1, 2)


        # finish setup
        main_layout.addWidget(self.controls_container)
        self.setLayout(main_layout)


    def updatePosition(self, pos_type, x, y, new_wco):
        '''Called when position OR wco updates.'''
        # If `WPos:` is given, use `MPos = WPos + WCO`.
        # If `MPos:` is given, use `WPos = MPos - WCO`.

        if not new_wco:     # empty if not given
            wco_x, wco_y = self.sample_coordinate_offset
        else:
            wco_x, wco_y = new_wco

        if pos_type == "WPos":
            
            self.current_wpos_x = x
            self.current_wpos_y = y

            self.current_mpos_x = x + wco_x
            self.current_mpos_y = y + wco_y


        elif pos_type == "MPos":
            self.current_mpos_x = x
            self.current_mpos_y = y

            self.current_wpos_x = x - wco_x
            self.current_wpos_y = x - wco_y
            
        
        # Update the GUI readout label
        self.lbl_pos.setText(
            f"Absolute (MPos) -> X: {self.current_mpos_x:.2f}, Y: {self.current_mpos_y:.2f}\n"
            f"Sample   (WPos) -> X: {self.current_wpos_x:.2f}, Y: {self.current_wpos_y:.2f}"
        )

    def updateWorkCoordinateOffset(self, wco_x, wco_y):
        # update model
        self.sample_coordinate_offset = (wco_x, wco_y)
        self.updatePosition("WPos", self.current_wpos_x, self.current_wpos_y, [wco_x, wco_y])


    def updateStatus(self, status):
        self.status = status
        self.isMoving = status not in self.NOT_MOVING_STATUSES

        if status == 'Alarm':
            print("! ALARM TRIGGERED !\nHome machine to continue, or restart program.")


    def handleRasterFinished(self):
        self.toggle_movement_btn.setChecked(False)


    def cancelRaster(self):
        # Add to button if a soft cancel is desired
        # Finishes current movement and cancels all queued commands

        self.serial.clear_command_queue()
        self.toggle_movement_btn.setChecked(False)


    def handleToggleMovement(self, isChecked):
        '''Sends either `!` feed hold or `~` cycle resume.
        Note: Does not work on homing or alarm state.'''

        if isChecked:
            # Stop movement
            self.serial.send_immediate('!')
            self.toggle_movement_btn.setText("Resume")
        else:
            # Resume movement
            self.serial.send_immediate('~')
            self.toggle_movement_btn.setText("Stop")



    def set_new_reference_point(self):
        # Input validation + call to update model
        stages_config = self.stages_config

        # exit if sample width and height not set
        if not stages_config.sample_dimensions_valid() or not stages_config.gantry_dimensions_valid():
            print("Sample and gantry config inputs must be an integer value.")
            return

        # exit if reference point exceeds stage bounds
        sample_width = float(stages_config.get_sample_width())
        sample_height = float(stages_config.get_sample_height())
        gantry_width = float(stages_config.get_gantry_width())
        gantry_height = float(stages_config.get_gantry_height())

        xbound = gantry_width - sample_width
        ybound = gantry_height - sample_height

        mpos_x = self.current_mpos_x
        mpos_y = self.current_mpos_y

        if mpos_x > xbound or mpos_y > ybound:
            print("Reference point cannot exceed stage bounds.")
            return


        # tell GRBL the new working position
        self.serial.set_working_coordinate_system(mpos_x, mpos_y)


    def set_sample_corner(self, corner: Literal['corner1', 'corner2']) -> None:
        """Captures current workspace positions and sets the specified sample corner.
        
        If both corners become populated, initializes or updates self.sample_endpoints.
        """
        current_pt = Point(x=self.current_wpos_x, y=self.current_wpos_y)
        
        # toggle set point logic
        if corner == 'corner1':
            if self.temp_corner1 is not None:
                self.temp_corner1 = None
                self.smeasure_c1_btn.setText("Corner 1")
                self.smeasure_start_label.setText("Corner 1: --")
            else:
                self.temp_corner1 = current_pt
                self.smeasure_c1_btn.setText("Clear Corner 1")
                self.smeasure_start_label.setText(f"X: {current_pt.x}, Y: {current_pt.y}")

        elif corner == 'corner2':
            if self.temp_corner2 is not None:
                self.temp_corner2 = None
                self.smeasure_c2_btn.setText("Corner 2")
                self.smeasure_end_label.setText("Corner 2: --")
            else:
                self.temp_corner2 = current_pt
                self.smeasure_c2_btn.setText("Clear Corner 2")
                self.smeasure_end_label.setText(f"X: {current_pt.x}, Y: {current_pt.y}")
        else:
            raise ValueError(f"Invalid corner specifier: {corner}. Expected 'corner1' or 'corner2'.")


    def toggle_manual_measurement(self, checked):
        
        if checked:
            # Begin Measurement

            # Enable corner buttons
            self.smeasure_c1_btn.setEnabled(True)
            self.smeasure_c2_btn.setEnabled(True)
            self.smeasure_toggle_btn.setText("End Measurement")
        else:
            # End Measurement

            # validate sample corners
            self.sample_endpoints = SpanEndpoints(
                corner1=self.temp_corner1,
                corner2=self.temp_corner2
            )

            try:
                self.sample_endpoints.validate_points()
            except ValueError as e:
                print(f"Cannot set sample measurement with invalid points: {e}")
                self.sample_endpoints = SpanEndpoints(
                    Point(None, None),
                    Point(None, None)
                )

                self.smeasure_toggle_btn.setChecked(True)
                return

        
            # Disable corner buttons
            self.smeasure_c1_btn.setEnabled(False)
            self.smeasure_c2_btn.setEnabled(False)

            self.smeasure_start_label.setText("X: --, Y: --")
            self.smeasure_end_label.setText("X: --, Y: --")

            # apply dimensions to line inputs
            self.stages_config.setWidth(str(self.sample_endpoints.width))
            self.stages_config.setHeight(str(self.sample_endpoints.height))

            # clear temp inputs
            self.temp_corner1 = None
            self.temp_corner2 = None

            self.smeasure_toggle_btn.setText("Begin Measuring Sample Dimensions")


    def start_scan(self):
        def stage_to_motor_speed(stage_spd):
            '''Assumes input speed is mm/second.
            Output speed is in mm/min.
            CoreXY formula: motor speed = half of stage speed
            '''

            return (stage_spd/2) * 60


        # --- input validation ---
        if not self.stages_config.sample_dimensions_valid():
            print("Cannot start scan without valid sample dimensions.")
            return
        
        if not self.scan_resolution.text().strip():
            print("Cannot start scan without resolution input.")
            return

        spd = self.scan_speed.text().strip()
        if not spd:
            print("Input speed before starting scan.")
            return

        if not float(spd):
            print("Input speed must be an integer.")
            return

        spd = float(spd)
        if spd < self.MIN_STAGE_SPEED or spd > self.MAX_STAGE_SPEED:
            print(f'Scan speed must be within the limit: [{self.MIN_STAGE_SPEED}, {self.MAX_STAGE_SPEED}] mm/min')
            return
    
        sampleWidth = float(self.stages_config.get_sample_width())
        sampleHeight = float(self.stages_config.get_sample_height())
        resolution = float(self.scan_resolution.text().strip())
        feed_rate = stage_to_motor_speed(spd)

        commands = generate_raster_commands(sampleWidth, sampleHeight, resolution, feed_rate).split('\n')
        self.serial.send_batch_commands(commands)


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

        self.serial.jog(axis, change, self.JOG_SPEED)


    def go_to_part_zero(self):
        '''Returns to (0, 0) with respect to *sample* coordinates.
        Requires sample coordinate system (G54) to be defined.
        '''

        x = self.current_wpos_x
        y = self.current_wpos_y

        if self.isMoving:
            print("Wait until movement is finished")
            return

        self.serial.pseudo_home(x, y, self.SAMPLE_HOMING_SPEED)


    def home(self):
        '''Sends $H to begin homing sequence.
        
        If pseudohoming: Returns to (0, 0) based on
        distance travelled away from home.
        
        '''

        use_pseudo_homing = True    # set false if limit switch homing works

        if self.isMoving:
            print("Wait until movement is finished")
            return

        if not use_pseudo_homing:
            self.serial.send_command("$H")
        else:
            self.serial.pseudo_home(self.current_mpos_x, self.current_mpos_y, self.PHYSICAL_HOMING_SPEED)


    def populate_ports(self):
        """Scans for available serial ports and populates the dropdown."""
        self.port_combo.clear()
        
        ports = self.serial.list_available_ports()
        
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
        self.controls_container.setEnabled(True)


    def toggle_connection(self):
        if not self.serial.port_open():
            try:
                selected_port = self.get_selected_port()

                self.serial.connect_to(selected_port)
                self.btn_connect.setText('Disconnect')

                self.onConnect()

            except Exception as e:
                print(f"Connection Error: {e}")
        else:

            # disable controls
            self.controls_container.setEnabled(False)

            self.serial.disconnect_port()
            self.btn_connect.setText('Connect')


    def closeEvent(self, event):
        # Stop background workers and close the serial port
        if hasattr(self, "serial"):
            self.serial.stop()
        event.accept()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    ex = CoreXYController()
    ex.show()
    sys.exit(app.exec())