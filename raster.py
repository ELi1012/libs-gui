



def generate_raster_commands(sampleWidth, sampleHeight, resolution: int, feedrate: int):
    '''Returns a series of g-code commands, separated by newlines.
    
    Assumes stage is at home position (wrt sample).
    Commands are in *relative* mode.
    
    sampleWidth: width to raster across (mm)
    sampleHeight: height to raster across (mm)
    resolution: resolution of scan, 
        ie. distance between consecutive shots (mm)
    feedrate: millimeters/min
    '''

    commands = ''
    rows = int(sampleHeight // resolution)
    go_right = True     # False -> go left

    def addCommand(newCommand):
        nonlocal commands
        commands += f'{newCommand}\n'

    addCommand('G21')   # set units to metric
    addCommand('G17')   # set XY plane
    addCommand('G91')   # set to relative positioning

    addCommand(f'F{feedrate}')

    for current_row in range(0, rows):
        x_movement = f'X{sampleWidth}' if go_right else f'X-{sampleWidth}'

        addCommand(f'G01 {x_movement} Y0')

        # do not move down if on final row
        if current_row < rows - 1:
            addCommand(f'G01 X0 Y{resolution}')

        # toggle left/right direction
        go_right = not go_right
    
    addCommand('G90')     # return to absolute positioning

    return commands





if __name__ == '__main__':
    width = 2
    height = 5

    commands = generate_raster_commands(width, height, 1, 1000)
    print(commands)
