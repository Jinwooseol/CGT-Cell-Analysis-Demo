# Progress Monitor Panel

## Overview

The Progress Monitor Panel is a new feature that displays the progress of multiple tests running simultaneously in the CGT Cell Analysis Demo. It provides a comprehensive view of all running tests with individual progress bars, status information, and summary statistics.

## Features

### 1. Multiple Test Display
- Shows all running tests in a scrollable interface
- Each test displays:
  - Job ID and Sample ID
  - Current status (Pending, Running, Done, Failed)
  - Data availability (Optical/PCR)
  - Current step and progress percentage
  - Visual progress bar with color coding

### 2. Summary Statistics
- Total number of tests
- Number of running tests
- Number of completed tests
- Number of failed tests

### 3. Real-time Updates
- Automatically updates progress as tests run
- Color-coded status indicators
- Progress bars that change color based on status:
  - Blue: Running
  - Green: Completed
  - Red: Failed

### 4. Panel Switching
- Switch between Pipeline Panel and Progress Monitor
- Automatic switching when tests start running
- Manual switching via buttons

## Usage

### Automatic Switching
- When "Run all" is clicked in the Control Panel, the view automatically switches to the Progress Monitor
- When individual steps are run from the Pipeline Panel, the view switches to the Progress Monitor

### Manual Switching
- **From Pipeline Panel**: Click "View Progress Monitor" button
- **From Progress Monitor**: Click "Switch to Pipeline" button

### Adding Tests
Tests are automatically added to the Progress Monitor when:
- A new job is added to the batch manager
- Individual pipeline steps are executed

## Implementation Details

### Files Modified/Created
1. **`CGT Cell Analysis Demo/ui/panels/progress_monitor_panel.py`** - New progress monitor panel
2. **`CGT Cell Analysis Demo/ui/main_window.py`** - Integration with main window
3. **`CGT Cell Analysis Demo/ui/panels/pipeline_panel.py`** - Added switch button

### Key Classes
- `ProgressMonitorPanel`: Main panel class for displaying test progress
- `TestJob`: Model class representing individual test jobs
- `JobStatus`: Enum for test status (pending, running, done, failed)

### Signals and Slots
- `switch_to_pipeline`: Signal to switch back to pipeline panel
- `log`: Signal for logging messages
- Progress updates are connected to job progress handlers

## Demo

A demo script `demo_progress_monitor.py` is provided to demonstrate the functionality:

```bash
python demo_progress_monitor.py
```

This demo allows you to:
- Add test jobs
- Update their progress
- Clear all tests
- See the real-time updates

## Styling

The panel uses a modern, clean design with:
- Card-based layout for individual tests
- Color-coded status indicators
- Responsive progress bars
- Professional color scheme
- Hover effects on buttons

## Future Enhancements

Potential improvements could include:
- Test filtering and sorting
- Detailed test logs
- Export functionality
- Test history
- Performance metrics
- Real-time notifications
