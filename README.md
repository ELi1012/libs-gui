# About

App to control movement of portable LIBS stage.


> Note on homing and emergency stops:
> Do not use "Home Machine" unless limit switches are implemented.
> Otherwise, stage will run into physical edge and cause belt slippage and potential damage.
> 
> Using "Emergency Stop" button will send FluidNC into an alarm state,
> which cannot be deactivated without either homing the machine or sending the `$X` unlock command (not implemented).
> Best option is to disconnect the board entirely and start again.
> It may be necessary to open the ESP32 terminal and send `$X` to unlock the alarm,
> assuming the board doesn't always boot up in an alarm state. If it does, open the FluidNC config
> and set `$start/must_home:false` <- not recommended unless testing without limit switches



# Quickstart

From your terminal:
```
# Create virtual env
python3 -m venv venv
source venv/bin/activate    # command to activate venv may differ across machines

# Install requirements
python3 -m pip install -r requirements.txt

# Open app
python3 app.py
```


# Example Workflow


**Connect FluidNC Board**
1. Plug FluidNC board into laptop
2. Hit "Refresh" button
3. Select port from dropdown
4. Hit "Connect"

**Set Sample Dimensions**
1. Hit "Begin Measuring Sample Dim."
2. Go to *Manual Controls*
3. Move stage to sample corner using arrow keys
4. Return to *Measure Sample Manually*
5. Hit "Corner 1"
6. Repeat steps 2-4 for opposite corner of sample
7. Hit "End Measurement"
8. Outcome: Under *Sample Size*, width and height are updated with sample dimensions

**Set Sample Home**
1. Go to *Manual Controls*
2. Move stage to where sample should begin analysis
3. Hit "Set Ref. Point"
4. Outcome: "Return to Ref. Point" should return stage to position set in Step 3


**Start Scan**
1. Hit "START SCAN"
2. To pause/resume motion: Hit "Stop" button next to "START SCAN"

