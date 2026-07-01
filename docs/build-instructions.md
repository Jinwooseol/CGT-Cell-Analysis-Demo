# Building CGT Cell Analysis Demo Executable

This document provides instructions for building the CGT Cell Analysis Demo into a standalone executable file.

## Perfect Configuration Features

The build system uses optimized PyInstaller spec files that include:

- ✅ **Complete PySide6 Support**: All plugins, platforms, imageformats, styles, translations, and QML
- ✅ **PyTorch Integration**: Dynamic libraries, metadata, and proper submodule collection
- ✅ **Optimized Compression**: UPX compression with exclusions for problematic libraries
- ✅ **Complete Dependencies**: All Python packages, metadata, and hidden imports
- ✅ **Resource Bundling**: Icons, models, reference data, and configuration files
- ✅ **Error Prevention**: Proper handling of PyInstaller version differences

## Prerequisites

- Python 3.8 or higher
- All dependencies from `requirements.txt` installed
- Windows 10/11 (for Windows executable)
- Virtual environment recommended (included: `myenv/`)

## Quick Start

### Method 1: Using the Build Script (Recommended)

1. **Activate virtual environment:**
   ```bash
   .\myenv\Scripts\activate
   ```

2. **Build the executable:**
   ```bash
   python build_exe.py
   ```

3. **Run the executable:**
   ```bash
   .\dist\CGT Cell Analysis Demo\CGT Cell Analysis Demo.exe
   ```

### Method 2: Using Batch Files (Easiest)

1. **For virtual environment builds:**
   ```bash
   build_with_venv.bat
   ```

2. **For direct builds:**
   ```bash
   build_and_distribute.bat
   ```

### Method 3: Using PyInstaller Directly

1. **Install PyInstaller:**
   ```bash
   pip install pyinstaller
   ```

2. **Build using the perfect spec file:**
   ```bash
   pyinstaller CGT Cell Analysis Demo.spec
   ```

3. **Run the executable:**
   ```bash
   .\dist\CGT Cell Analysis Demo\CGT Cell Analysis Demo.exe
   ```

## Build Options

### Build Script Options

The `build_exe.py` script supports several options with perfect configuration:

```bash
# Clean build directories before building
python build_exe.py --clean

# Build in debug mode (shows console output)
python build_exe.py --debug

# Build as single file executable (larger but portable)
python build_exe.py --onefile

# Combine options
python build_exe.py --clean --debug --onefile
```

### Build Modes

#### Directory Mode (Default) - Perfect Configuration
- Creates a folder with the executable and all dependencies
- Uses `CGT Cell Analysis Demo.spec` with perfect configuration
- Faster startup time (no extraction needed)
- Complete PySide6 plugin support
- Recommended for development and testing

#### Single File Mode (`--onefile`) - Perfect Configuration
- Creates a single executable file
- Uses `CGT Cell Analysis Demo_onefile.spec` with perfect configuration
- Larger file size but completely portable
- Slower startup time (extracts files to temp directory)
- Better for distribution
- Same perfect configuration as directory mode

## File Structure After Build

### Directory Mode
```
dist/
└── CGT Cell Analysis Demo/
    ├── CGT Cell Analysis Demo.exe          # Main executable
    ├── CGT Cell Analysis Demo/             # Application resources
    │   ├── resources/       # Icons and assets
    │   ├── core/           # Core modules
    │   ├── ui/             # UI modules
    │   └── ...
    ├── reference_data/     # Reference data files
    ├── models/             # AI model files
    ├── config.json         # Configuration
    └── [dependencies]      # Python libraries
```

### Single File Mode
```
dist/
└── CGT Cell Analysis Demo.exe             # Single executable file
```

## Troubleshooting

### Perfect Configuration Benefits

The perfect configuration spec files resolve most common issues:

- ✅ **GUI Display Issues**: Complete PySide6 plugin support prevents GUI not appearing
- ✅ **PyTorch Loading**: Dynamic libraries and metadata ensure AI models load correctly
- ✅ **Image Format Support**: Complete imageformats plugin support
- ✅ **Missing Dependencies**: Comprehensive hidden imports collection
- ✅ **Compression Issues**: Optimized UPX settings with proper exclusions

### Common Issues (Rare with Perfect Configuration)

1. **"Module not found" errors:**
   - The perfect configuration includes comprehensive hidden imports
   - If still occurring, add missing modules to the `hiddenimports` list in spec files
   - Rebuild the executable

2. **Large executable size:**
   - Use directory mode instead of single file mode
   - Perfect configuration already optimizes compression
   - Check if unnecessary modules are being included

3. **Missing data files:**
   - Perfect configuration includes all necessary data files
   - Add missing files to the `datas` list in spec files if needed
   - Ensure file paths are correct

4. **PyTorch issues:**
   - Perfect configuration includes PyTorch dynamic libraries
   - Make sure PyTorch is installed with CPU support if you don't need GPU
   - For smaller builds, consider using CPU-only PyTorch

### Debug Mode

If the executable doesn't work properly, build in debug mode to see error messages:

```bash
python build_exe.py --debug
```

This will show console output and help identify issues. The perfect configuration should prevent most problems.

### Performance Optimization

The perfect configuration already includes optimizations:

1. **File size optimization:**
   - UPX compression enabled with proper exclusions
   - Directory mode recommended for smaller total size
   - Optimized PyTorch library inclusion

2. **Startup optimization:**
   - Directory mode provides faster startup
   - Proper plugin loading prevents delays
   - Optimized compression settings

## Advanced Configuration

### Perfect Spec Files

Both spec files (`CGT Cell Analysis Demo.spec` and `CGT Cell Analysis Demo_onefile.spec`) are perfectly configured:

- **Complete PySide6 Support**: All plugins, platforms, imageformats, styles, translations, QML
- **PyTorch Integration**: Dynamic libraries, metadata, submodule collection
- **Data Files**: Resources, models, reference data, configuration
- **Hidden Imports**: Comprehensive collection of all required modules
- **Compression**: Optimized UPX with exclusions for problematic libraries

### Modifying the Spec Files

If you need to customize the perfect configuration:

- **Data files:** Add/remove files in the `datas` list
- **Hidden imports:** Add modules to the `hiddenimports` list
- **Exclusions:** Modify UPX exclusions if needed
- **Console mode:** Change `console=False` to `console=True` for debug output

### Custom Build Script

The `build_exe.py` script is optimized for the perfect configuration and includes:
- Dependency verification
- Project structure validation
- Enhanced error reporting
- Perfect configuration information

## Distribution

### Perfect Configuration Benefits

**All dependencies are automatically included** with perfect configuration:
- ✅ Python interpreter and standard library
- ✅ Complete PySide6 framework with all plugins
- ✅ PyTorch AI models and machine learning libraries
- ✅ All packages from `requirements.txt`
- ✅ Your application code and resources
- ✅ AI models and reference data
- ✅ Configuration files and metadata
- ✅ Optimized compression and startup

**Recipients need:**
- ❌ No Python installation
- ❌ No pip or package management
- ❌ No additional software
- ❌ No compatibility concerns (perfect configuration handles everything)

### Creating Distribution Package

Use the distribution creator for easy sharing with perfect configuration:

```bash
# Create a complete distribution package
python create_distribution.py

# Create single-file distribution
python create_distribution.py --onefile

# Include debug information
python create_distribution.py --debug
```

This creates a ZIP file with:
- The executable with perfect configuration
- User-friendly README with troubleshooting
- License information
- Simple batch file to run the app
- Complete dependency support

### Manual Distribution

1. **Directory mode:** Distribute the entire `dist/CGT Cell Analysis Demo/` folder
2. **Single file mode:** Distribute only the `CGT Cell Analysis Demo.exe` file

Both modes include perfect configuration for maximum compatibility.

### Installation for End Users

End users simply:
1. Extract the ZIP file (if using distribution package)
2. Run `CGT Cell Analysis Demo.exe`
3. No Python installation required!
4. Perfect configuration ensures compatibility across Windows systems

### System Requirements for End Users

- Windows 10/11 (64-bit)
- No additional software required
- Sufficient disk space for the executable and temporary files
- Perfect configuration handles all compatibility issues

## File Sizes

Typical file sizes with perfect configuration (approximate):
- Directory mode: 200-500 MB total
- Single file mode: 300-800 MB executable

The exact size depends on:
- PyTorch version (CPU vs GPU)
- Included data files
- Perfect configuration optimizations

## Support

If you encounter issues during the build process:

1. Check the console output for error messages
2. Try building in debug mode: `python build_exe.py --debug`
3. Verify all dependencies are installed
4. Check that all required files exist in the project directory
5. The perfect configuration should resolve most issues automatically

## Perfect Configuration Summary

The build system now uses **perfect configuration** that includes:

- **Complete PySide6 Support**: All plugins, platforms, imageformats, styles, translations, QML
- **PyTorch Integration**: Dynamic libraries, metadata, proper submodule collection
- **Optimized Compression**: UPX with exclusions for problematic libraries
- **Comprehensive Dependencies**: All Python packages, metadata, hidden imports
- **Resource Bundling**: Icons, models, reference data, configuration files
- **Error Prevention**: Proper PyInstaller version handling

This ensures maximum compatibility, performance, and reliability across all Windows systems.
