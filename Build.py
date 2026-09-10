import ast
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


# ============================================================
# Configuration
# ============================================================

if getattr(sys, "frozen", False):
    APP_DIR = Path(sys.executable).resolve().parent
else:
    APP_DIR = Path(__file__).resolve().parent

BUILDER_EXE_NAME = "Python EXE Builder"


# ============================================================
# General utilities
# ============================================================

def pause():
    input("\nPress Enter to continue...")


def clear_screen():
    os.system("cls" if os.name == "nt" else "clear")


def is_frozen():
    return getattr(sys, "frozen", False)


def clean_input(value):
    """
    Remove whitespace and surrounding quotation marks.

    This allows paths such as:

        E:\Scripts\Test.py

    and:

        "E:\Scripts\Test.py"
    """

    return value.strip().strip('"').strip("'")


def format_command(command):
    result = []

    for item in command:
        item = str(item)

        if " " in item:
            result.append(f'"{item}"')
        else:
            result.append(item)

    return " ".join(result)


def run_command(command, cwd=None):
    print()
    print("Running:")
    print(format_command(command))
    print()

    result = subprocess.run(
        command,
        cwd=cwd,
    )

    return result.returncode


# ============================================================
# Output directory
# ============================================================

def select_output_directory(default_directory):
    default_directory = Path(default_directory).resolve()

    print()
    print("Output directory")
    print("=" * 60)
    print()

    print("This is where the finished EXE will be placed.")
    print()

    print("Default:")
    print(f"  {default_directory}")
    print()

    print("Enter a path, or press Enter to use the default.")
    print()

    while True:
        choice = clean_input(
            input("Output directory: ")
        )

        if not choice:
            output_directory = default_directory
        else:
            output_directory = Path(
                os.path.expandvars(choice)
            ).expanduser()

            if not output_directory.is_absolute():
                output_directory = APP_DIR / output_directory

            output_directory = output_directory.resolve()

        try:
            output_directory.mkdir(
                parents=True,
                exist_ok=True,
            )
        except OSError as error:
            print()
            print("Could not create/access that directory.")
            print(f"Reason: {error}")
            print()
            continue

        if not output_directory.is_dir():
            print()
            print("That path is not a directory.")
            print()
            continue

        print()
        print("Output directory:")
        print(f"  {output_directory}")

        return output_directory


# ============================================================
# Open output directory
# ============================================================

def ask_open_output_directory(output_directory):
    print()

    choice = clean_input(
        input("Open output folder? [Y/n]: ")
    ).lower()

    if choice and choice != "y":
        return

    try:
        if os.name == "nt":
            os.startfile(str(output_directory))

        elif sys.platform == "darwin":
            subprocess.Popen(
                ["open", str(output_directory)]
            )

        else:
            subprocess.Popen(
                ["xdg-open", str(output_directory)]
            )

    except Exception as error:
        print()
        print("Could not open the output folder automatically.")
        print(f"Reason: {error}")


# ============================================================
# Remove previous output
# ============================================================

def remove_previous_output(
    output_directory,
    exe_name,
    onedir=False,
):
    if onedir:
        target = (
            output_directory
            / Path(exe_name).stem
        )
    else:
        target = output_directory / exe_name

    if not target.exists():
        return True

    print()
    print("Removing previous build:")
    print(f"  {target}")

    try:
        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink()

        print("Previous build removed.")
        return True

    except Exception as error:
        print()
        print("Could not remove the previous build.")
        print(f"Reason: {error}")
        print()
        print("Make sure the previous EXE isn't running.")
        pause()
        return False


# ============================================================
# Python interpreter detection
# ============================================================

def get_python_candidates():
    candidates = []

    def add_candidate(command):
        normalized = tuple(
            str(x).lower()
            for x in command
        )

        for existing in candidates:
            existing_normalized = tuple(
                str(x).lower()
                for x in existing
            )

            if existing_normalized == normalized:
                return

        candidates.append(command)

    if not is_frozen():
        add_candidate([sys.executable])
        return candidates

    if os.name == "nt":
        py_launcher = shutil.which("py")

        if py_launcher:
            add_candidate(
                [py_launcher, "-3"]
            )

    for command_name in (
        "python",
        "python3",
    ):
        executable = shutil.which(command_name)

        if executable:
            add_candidate([executable])

    local_app_data = os.environ.get(
        "LOCALAPPDATA"
    )

    if local_app_data:
        python_root = (
            Path(local_app_data)
            / "Programs"
            / "Python"
        )

        if python_root.exists():
            for python_dir in sorted(
                python_root.glob("Python*"),
                reverse=True,
            ):
                python_exe = (
                    python_dir
                    / "python.exe"
                )

                if python_exe.exists():
                    add_candidate(
                        [str(python_exe)]
                    )

    user_profile = os.environ.get(
        "USERPROFILE"
    )

    if user_profile:
        scoop_python = (
            Path(user_profile)
            / "scoop"
            / "apps"
            / "python"
            / "current"
            / "python.exe"
        )

        if scoop_python.exists():
            add_candidate(
                [str(scoop_python)]
            )

    return candidates


def python_has_module(
    python_command,
    module_name,
):
    try:
        result = subprocess.run(
            python_command
            + [
                "-c",
                (
                    "import importlib.util; "
                    f"print(importlib.util.find_spec("
                    f"{module_name!r}) is not None)"
                ),
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )

        return (
            result.returncode == 0
            and result.stdout.strip().lower() == "true"
        )

    except (
        OSError,
        subprocess.SubprocessError,
    ):
        return False


def detect_builders():
    candidates = get_python_candidates()

    for python_command in candidates:
        pyinstaller = python_has_module(
            python_command,
            "PyInstaller",
        )

        py2exe = python_has_module(
            python_command,
            "py2exe",
        )

        if pyinstaller or py2exe:
            return (
                python_command,
                pyinstaller,
                py2exe,
            )

    return (
        None,
        False,
        False,
    )


# ============================================================
# Dependency detection
# ============================================================

def extract_imports(script):
    try:
        source = script.read_text(
            encoding="utf-8-sig"
        )

        tree = ast.parse(
            source,
            filename=str(script),
        )

    except UnicodeDecodeError:
        source = script.read_text(
            encoding="cp1252"
        )

        tree = ast.parse(
            source,
            filename=str(script),
        )

    except SyntaxError as error:
        print()
        print(
            "Could not analyse the script because it "
            "contains a Python syntax error."
        )

        print()
        print(f"Line: {error.lineno}")
        print(f"Error: {error.msg}")

        return []

    imports = set()

    for node in ast.walk(tree):

        if isinstance(node, ast.Import):

            for alias in node.names:
                if alias.name:
                    imports.add(
                        alias.name.split(".")[0]
                    )

        elif isinstance(node, ast.ImportFrom):

            if node.level and node.level > 0:
                continue

            if node.module:
                imports.add(
                    node.module.split(".")[0]
                )

    return sorted(
        imports,
        key=str.lower,
    )


def check_module_with_python(
    python_command,
    module_name,
    script_directory,
):
    code = r'''
import importlib.util
import importlib.metadata
import sys

module_name = sys.argv[1]

spec = importlib.util.find_spec(module_name)

if spec is None:
    print("MISSING")
    sys.exit(0)

distribution_names = []

try:
    package_map = importlib.metadata.packages_distributions()
    distribution_names = package_map.get(module_name, [])
except Exception:
    pass

print("FOUND")

if distribution_names:
    print("|".join(distribution_names))
else:
    print("")
'''

    try:
        result = subprocess.run(
            python_command
            + [
                "-c",
                code,
                module_name,
            ],
            cwd=str(script_directory),
            capture_output=True,
            text=True,
            timeout=15,
        )

        if result.returncode != 0:
            return {
                "found": False,
                "distribution": None,
            }

        lines = (
            result.stdout
            .strip()
            .splitlines()
        )

        if not lines:
            return {
                "found": False,
                "distribution": None,
            }

        found = (
            lines[0].strip()
            == "FOUND"
        )

        distribution = None

        if len(lines) >= 2:
            distribution = (
                lines[1].strip()
                or None
            )

        return {
            "found": found,
            "distribution": distribution,
        }

    except (
        OSError,
        subprocess.SubprocessError,
    ):
        return {
            "found": False,
            "distribution": None,
        }


def check_dependencies(
    script,
    python_command,
):
    print()
    print("=" * 60)
    print("DEPENDENCY CHECK")
    print("=" * 60)
    print()

    print("Analysing Python imports...")

    imports = extract_imports(script)

    if not imports:
        print()
        print("No imports were detected.")
        return []

    print()
    print(
        f"Found {len(imports)} imported module(s)."
    )

    missing = []

    for module_name in imports:

        result = check_module_with_python(
            python_command,
            module_name,
            script.parent,
        )

        if result["found"]:

            print(
                f"  [OK]      {module_name}"
            )

        else:

            print(
                f"  [MISSING] {module_name}"
            )

            missing.append(
                {
                    "module": module_name,
                    "distribution": result[
                        "distribution"
                    ],
                }
            )

    print()

    if missing:

        print(
            "Missing dependencies detected:"
        )

        print()

        for item in missing:
            print(
                f"  - {item['module']}"
            )

        print()

    else:

        print(
            "All detected dependencies are available."
        )

    return missing


# ============================================================
# Known PyPI package names
# ============================================================

KNOWN_PACKAGE_NAMES = {
    "PIL": "Pillow",
    "cv2": "opencv-python",
    "yaml": "PyYAML",
    "bs4": "beautifulsoup4",
    "Crypto": "pycryptodome",
    "win32api": "pywin32",
    "win32con": "pywin32",
    "win32gui": "pywin32",
    "win32process": "pywin32",
    "win32com": "pywin32",
    "serial": "pyserial",
    "dotenv": "python-dotenv",
    "dateutil": "python-dateutil",
}


def choose_pypi_package(module_name):

    suggested = KNOWN_PACKAGE_NAMES.get(
        module_name,
        module_name,
    )

    print()
    print(
        f"Missing module: {module_name}"
    )

    print(
        f"Suggested PyPI package: {suggested}"
    )

    print()

    print(
        "If this module comes from a differently named "
        "PyPI package, enter that package name instead."
    )

    print()

    choice = clean_input(
        input(
            f"PyPI package [{suggested}]: "
        )
    )

    if not choice:
        return suggested

    return choice


def install_missing_dependencies(
    missing,
    python_command,
):
    if not missing:
        return True

    print()
    print("=" * 60)
    print("MISSING DEPENDENCIES")
    print("=" * 60)
    print()

    print(
        "The following modules are required by the script"
    )

    print(
        "but are not installed in the Python environment"
    )

    print(
        "being used for the build:"
    )

    print()

    for item in missing:
        print(
            f"  - {item['module']}"
        )

    print()

    choice = clean_input(
        input(
            "Attempt to install them with pip? [Y/n]: "
        )
    ).lower()

    if choice and choice != "y":

        print()
        print(
            "Dependency installation skipped."
        )

        return False

    for item in missing:

        module_name = item["module"]

        package_name = choose_pypi_package(
            module_name
        )

        print()
        print(
            f"Installing {package_name}..."
        )

        command = python_command + [
            "-m",
            "pip",
            "install",
            package_name,
        ]

        return_code = run_command(
            command
        )

        if return_code != 0:

            print()
            print(
                f"Failed to install: {package_name}"
            )

        else:

            print()
            print(
                f"Successfully installed: {package_name}"
            )

    return True


def dependency_check_and_install(
    script,
    python_command,
):
    missing = check_dependencies(
        script,
        python_command,
    )

    if not missing:
        return True

    install_missing_dependencies(
        missing,
        python_command,
    )

    print()
    print("=" * 60)
    print("RE-CHECKING DEPENDENCIES")
    print("=" * 60)

    missing_after_install = (
        check_dependencies(
            script,
            python_command,
        )
    )

    if missing_after_install:

        print()
        print(
            "WARNING: Some dependencies are still missing."
        )

        print()

        for item in missing_after_install:
            print(
                f"  - {item['module']}"
            )

        print()

        print(
            "The EXE may fail to start unless these"
        )

        print(
            "dependencies are supplied separately."
        )

        print()

        choice = clean_input(
            input(
                "Continue with the build anyway? [y/N]: "
            )
        ).lower()

        if choice != "y":

            print()
            print(
                "Build cancelled because dependencies "
                "could not be resolved."
            )

            pause()

            return False

        print()
        print(
            "Continuing with unresolved dependencies..."
        )

    return True


# ============================================================
# PyInstaller warning analysis
# ============================================================

def find_pyinstaller_warning_file(
    work_directory,
    application_name,
):
    possible = (
        work_directory
        / application_name
        / f"warn-{application_name}.txt"
    )

    if possible.exists():
        return possible

    matches = list(
        work_directory.rglob(
            "warn-*.txt"
        )
    )

    if matches:
        return matches[0]

    return None


def analyse_pyinstaller_warnings(
    warning_file,
):
    if not warning_file:
        return []

    if not warning_file.exists():
        return []

    try:
        text = warning_file.read_text(
            encoding="utf-8",
            errors="replace",
        )

    except OSError:
        return []

    missing = []

    for line in text.splitlines():

        line = line.strip()

        if not line:
            continue

        if not line.lower().startswith(
            "missing module named"
        ):
            continue

        remainder = line[
            len("missing module named"):
        ].strip()

        remainder = (
            remainder
            .strip('"')
            .strip("'")
        )

        if remainder:
            missing.append(remainder)

    return sorted(
        set(missing),
        key=str.lower,
    )


# ============================================================
# Builder selection
# ============================================================

def select_builder():

    (
        python_command,
        pyinstaller,
        py2exe,
    ) = detect_builders()

    print()
    print("Python / EXE builder detection")
    print("=" * 60)
    print()

    if python_command is None:

        print(
            "Could not find a Python installation containing "
            "PyInstaller or py2exe."
        )

        print()

        print("Install PyInstaller with:")
        print()
        print(
            "  python -m pip install pyinstaller"
        )

        print()

        print("Or install py2exe with:")
        print()
        print(
            "  python -m pip install py2exe"
        )

        pause()

        return None

    print("Python interpreter:")
    print()

    print(
        f"  {format_command(python_command)}"
    )

    print()

    print("EXE builders detected:")
    print()

    print(
        "  PyInstaller: "
        + (
            "Installed"
            if pyinstaller
            else "Not installed"
        )
    )

    print(
        "  py2exe:      "
        + (
            "Installed"
            if py2exe
            else "Not installed"
        )
    )

    print()

    if pyinstaller and not py2exe:

        print(
            "Only PyInstaller is installed."
        )

        print(
            "Using PyInstaller automatically."
        )

        return "pyinstaller"

    if py2exe and not pyinstaller:

        print(
            "Only py2exe is installed."
        )

        print(
            "Using py2exe automatically."
        )

        return "py2exe"

    print(
        "Both builders are installed."
    )

    print()

    print("  1. PyInstaller")
    print("  2. py2exe")

    print()

    while True:

        choice = clean_input(
            input(
                "Which builder would you like to use? [1]: "
            )
        )

        if not choice or choice == "1":
            return "pyinstaller"

        if choice == "2":
            return "py2exe"

        print(
            "Please enter 1 or 2."
        )


# ============================================================
# Python script selection
# ============================================================

def find_python_scripts():

    current_script = (
        Path(__file__).resolve()
        if not is_frozen()
        else None
    )

    scripts = []

    for file in APP_DIR.glob("*.py"):

        resolved = file.resolve()

        # Never list the source file when running build.py.
        if (
            current_script is not None
            and resolved == current_script
        ):
            continue

        # When the builder is running as an EXE, its original
        # Build.py source is normally beside it. Don't offer
        # that as the default script.
        if (
            is_frozen()
            and file.name.lower() == "build.py"
        ):
            continue

        scripts.append(file)

    return sorted(
        scripts,
        key=lambda x: x.name.lower(),
    )


def select_script():

    scripts = find_python_scripts()

    print()
    print("Python script selection")
    print("=" * 60)
    print()

    if scripts:

        print(
            "Python scripts found in the builder folder:"
        )

        print()

        for number, script in enumerate(
            scripts,
            1,
        ):
            print(
                f"  {number}. {script.name}"
            )

        print()

        print(
            "You can also enter the full path to a Python script."
        )

        print()

        while True:

            # IMPORTANT:
            # clean_input() removes surrounding quotes so
            # Windows paths copied from Explorer work correctly.
            choice = clean_input(
                input(
                    "Script to build [1]: "
                )
            )

            if not choice:
                return scripts[0]

            if choice.isdigit():

                number = int(choice)

                if 1 <= number <= len(scripts):
                    return scripts[number - 1]

                print(
                    f"Please enter a number between "
                    f"1 and {len(scripts)}."
                )

                continue

            path = Path(
                os.path.expandvars(choice)
            ).expanduser()

            if (
                path.is_file()
                and path.suffix.lower() == ".py"
            ):
                return path.resolve()

            print(
                "That isn't a valid Python script."
            )

    print(
        "No Python scripts were found in this folder."
    )

    print()

    print(
        "Enter the full path to the Python script."
    )

    print()

    while True:

        choice = clean_input(
            input("Script path: ")
        )

        path = Path(
            os.path.expandvars(choice)
        ).expanduser()

        if (
            path.is_file()
            and path.suffix.lower() == ".py"
        ):
            return path.resolve()

        print(
            "That isn't a valid Python script."
        )


# ============================================================
# Application type
# ============================================================

def select_application_type():

    print()
    print("Application type")
    print("-" * 60)
    print()

    print("  1. Windowed / GUI")
    print(
        "     No console window appears when the EXE starts."
    )

    print()

    print("  2. Console")
    print(
        "     A normal console window is attached."
    )

    print()

    while True:

        choice = clean_input(
            input(
                "Select application type [1]: "
            )
        )

        if not choice or choice == "1":
            return "windowed"

        if choice == "2":
            return "console"

        print(
            "Please enter 1 or 2."
        )


# ============================================================
# Package type
# ============================================================

def select_package_type(builder):

    print()
    print("Package type")
    print("-" * 60)
    print()

    if builder == "pyinstaller":

        print("  1. One-file EXE")
        print(
            "     Produces a single executable."
        )

        print()

        print("  2. Folder distribution")
        print(
            "     EXE and dependencies are placed in a folder."
        )

    else:

        print("  1. Standard folder")
        print(
            "     EXE and dependencies are placed in a folder."
        )

        print()

        print("  2. Bundled")
        print(
            "     Uses py2exe's bundled configuration."
        )

    print()

    while True:

        choice = clean_input(
            input(
                "Select package type [1]: "
            )
        )

        if not choice or choice == "1":

            if builder == "pyinstaller":
                return "onefile"

            return "folder"

        if choice == "2":

            if builder == "pyinstaller":
                return "folder"

            return "bundled"

        print(
            "Please enter 1 or 2."
        )


# ============================================================
# PyInstaller build
# ============================================================

def build_with_pyinstaller(
    script,
    application_type,
    package_type,
    python_command,
    output_directory,
    output_name=None,
):

    if python_command is None:
        raise RuntimeError(
            "No suitable Python interpreter was found."
        )

    name = (
        output_name
        if output_name
        else script.stem
    )

    is_onefile = (
        package_type == "onefile"
    )

    if not remove_previous_output(
        output_directory,
        f"{name}.exe",
        onedir=not is_onefile,
    ):
        return 1

    temp_work_dir = Path(
        tempfile.mkdtemp(
            prefix="pyinstaller_build_"
        )
    )

    try:

        command = python_command + [
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--clean",
            "--workpath",
            str(temp_work_dir),
            "--distpath",
            str(output_directory),
            "--specpath",
            str(temp_work_dir),
            "--name",
            name,
        ]

        if application_type == "windowed":
            command.append("--windowed")
        else:
            command.append("--console")

        if is_onefile:
            command.append("--onefile")
        else:
            command.append("--onedir")

        command.append(
            str(script)
        )

        return_code = run_command(
            command,
            cwd=APP_DIR,
        )

        warning_file = (
            find_pyinstaller_warning_file(
                temp_work_dir,
                name,
            )
        )

        warning_imports = (
            analyse_pyinstaller_warnings(
                warning_file
            )
        )

        if warning_imports:

            print()
            print("=" * 60)
            print("PYINSTALLER IMPORT WARNINGS")
            print("=" * 60)
            print()

            print(
                "PyInstaller reported these missing imports:"
            )

            print()

            for module_name in warning_imports:
                print(
                    f"  - {module_name}"
                )

            print()

            print(
                "Some PyInstaller warnings can be harmless,"
            )

            print(
                "especially for optional or platform-specific"
            )

            print(
                "modules."
            )

        return return_code

    finally:

        try:
            shutil.rmtree(
                temp_work_dir
            )
        except OSError:
            pass


# ============================================================
# py2exe build
# ============================================================

def build_with_py2exe(
    script,
    application_type,
    package_type,
    python_command,
    output_directory,
):

    if python_command is None:
        raise RuntimeError(
            "No suitable Python interpreter was found."
        )

    if application_type == "windowed":
        target_type = "windows"
    else:
        target_type = "console"

    if package_type == "bundled":
        bundle_files = 1
    else:
        bundle_files = 3

    if not remove_previous_output(
        output_directory,
        f"{script.stem}.exe",
        onedir=True,
    ):
        return 1

    temp_dir = Path(
        tempfile.mkdtemp(
            prefix="py2exe_build_"
        )
    )

    temp_setup = (
        temp_dir
        / "_temporary_py2exe_setup.py"
    )

    temp_build_dir = (
        temp_dir
        / "build"
    )

    try:

        setup_contents = f'''
from setuptools import setup
import py2exe

setup(
    name={script.stem!r},
    version="1.0.0",
    description="Built from {script.name}",
    {target_type}=[
        {{
            "script": {str(script)!r},
            "dest_base": {script.stem!r},
        }}
    ],
    options={{
        "py2exe": {{
            "compressed": True,
            "optimize": 1,
            "bundle_files": {bundle_files},
            "dist_dir": {str(output_directory)!r},
            "build_exe": {str(temp_build_dir)!r},
        }}
    }},
    zipfile=None,
)
'''

        temp_setup.write_text(
            setup_contents,
            encoding="utf-8",
        )

        command = python_command + [
            str(temp_setup),
            "py2exe",
        ]

        return run_command(
            command,
            cwd=temp_dir,
        )

    finally:

        try:
            shutil.rmtree(
                temp_dir
            )
        except OSError:
            pass


# ============================================================
# Build the builder itself
# ============================================================

def build_builder():

    if is_frozen():

        print()
        print(
            "The builder is already running as an EXE."
        )

        print()

        print(
            "Self-building is only available when running"
        )

        print(
            "the original build.py source file."
        )

        pause()

        return

    (
        python_command,
        pyinstaller,
        _,
    ) = detect_builders()

    if not pyinstaller:

        print()
        print(
            "PyInstaller is required to build the"
        )

        print(
            "EXE Builder itself."
        )

        print()

        print(
            "Install it with:"
        )

        print()

        print(
            "  python -m pip install pyinstaller"
        )

        pause()

        return

    print()
    print("=" * 60)
    print("BUILDING THE PYTHON EXE BUILDER")
    print("=" * 60)
    print()

    print("Original source:")
    print(
        f"  {Path(__file__).resolve()}"
    )

    print()

    print(
        "The original build.py will NOT be modified."
    )

    output_directory = (
        select_output_directory(
            APP_DIR
        )
    )

    temp_dir = Path(
        tempfile.mkdtemp(
            prefix="python_builder_"
        )
    )

    temp_script = (
        temp_dir
        / "python_exe_builder.py"
    )

    try:

        print()
        print(
            "Creating temporary source copy..."
        )

        shutil.copy2(
            Path(__file__).resolve(),
            temp_script,
        )

        print(
            f"  {temp_script}"
        )

        print()
        print(
            "Temporary source copy created successfully."
        )

        return_code = (
            build_with_pyinstaller(
                script=temp_script,
                application_type="console",
                package_type="onefile",
                python_command=python_command,
                output_directory=output_directory,
                output_name=BUILDER_EXE_NAME,
            )
        )

        if return_code != 0:

            print()
            print("=" * 60)
            print("BUILDER COMPILATION FAILED")
            print("=" * 60)
            print()

            print(
                f"PyInstaller exit code: {return_code}"
            )

            pause()

            return

    finally:

        try:

            shutil.rmtree(
                temp_dir
            )

            print()
            print(
                "Temporary source copy removed."
            )

        except OSError as error:

            print()
            print(
                "Warning: could not remove temporary directory:"
            )

            print(
                f"  {temp_dir}"
            )

            print()

            print(
                f"Reason: {error}"
            )

    exe_path = (
        output_directory
        / f"{BUILDER_EXE_NAME}.exe"
    )

    print()
    print("=" * 60)
    print("BUILDER CREATION COMPLETE")
    print("=" * 60)
    print()

    if exe_path.exists():

        size_mb = (
            exe_path.stat().st_size
            / (1024 * 1024)
        )

        print(
            "The builder EXE was created successfully!"
        )

        print()

        print(
            f"  {exe_path}"
        )

        print()

        print(
            f"Size: {size_mb:.2f} MB"
        )

        print()

        print(
            "Your original build.py remains unchanged."
        )

        ask_open_output_directory(
            output_directory
        )

    else:

        print(
            "PyInstaller completed, but the expected"
        )

        print(
            "builder EXE could not be found."
        )

        print()

        print("Expected:")
        print(
            f"  {exe_path}"
        )

        pause()


# ============================================================
# Normal script build
# ============================================================

def build_normal_script():

    builder = select_builder()

    if builder is None:
        return

    script = select_script()

    print()
    print("Selected script:")
    print(
        f"  {script}"
    )

    (
        python_command,
        _,
        _,
    ) = detect_builders()

    if python_command is None:

        print()
        print(
            "The Python interpreter could not be found."
        )

        pause()

        return

    # --------------------------------------------------------
    # Dependency check
    # --------------------------------------------------------

    if not dependency_check_and_install(
        script,
        python_command,
    ):
        return

    # --------------------------------------------------------
    # Application type
    # --------------------------------------------------------

    application_type = (
        select_application_type()
    )

    # --------------------------------------------------------
    # Package type
    # --------------------------------------------------------

    package_type = (
        select_package_type(
            builder
        )
    )

    # --------------------------------------------------------
    # Output directory
    # --------------------------------------------------------

    output_directory = (
        select_output_directory(
            script.parent
        )
    )

    # --------------------------------------------------------
    # Build summary
    # --------------------------------------------------------

    print()
    print("=" * 60)
    print("BUILD SUMMARY")
    print("=" * 60)
    print()

    print(
        f"Builder:      {builder}"
    )

    print(
        f"Script:       {script}"
    )

    print(
        "Application:  "
        + (
            "Windowed / No console"
            if application_type == "windowed"
            else "Console"
        )
    )

    if builder == "pyinstaller":

        print(
            "Package:      "
            + (
                "One-file EXE"
                if package_type == "onefile"
                else "Folder distribution"
            )
        )

    else:

        print(
            "Package:      "
            + (
                "Bundled"
                if package_type == "bundled"
                else "Folder distribution"
            )
        )

    print()

    print(
        f"Output:       {output_directory}"
    )

    print()

    confirm = clean_input(
        input(
            "Start build? [Y/n]: "
        )
    ).lower()

    if confirm and confirm != "y":

        print()
        print(
            "Build cancelled."
        )

        pause()

        return

    # --------------------------------------------------------
    # Build
    # --------------------------------------------------------

    print()
    print("=" * 60)
    print("BUILDING")
    print("=" * 60)

    if builder == "pyinstaller":

        return_code = (
            build_with_pyinstaller(
                script=script,
                application_type=application_type,
                package_type=package_type,
                python_command=python_command,
                output_directory=output_directory,
            )
        )

    else:

        return_code = (
            build_with_py2exe(
                script=script,
                application_type=application_type,
                package_type=package_type,
                python_command=python_command,
                output_directory=output_directory,
            )
        )

    if return_code != 0:

        print()
        print("=" * 60)
        print("BUILD FAILED")
        print("=" * 60)
        print()

        print(
            f"Builder exit code: {return_code}"
        )

        pause()

        return

    # --------------------------------------------------------
    # Determine resulting EXE
    # --------------------------------------------------------

    if builder == "pyinstaller":

        if package_type == "onefile":

            exe_path = (
                output_directory
                / f"{script.stem}.exe"
            )

        else:

            exe_path = (
                output_directory
                / script.stem
                / f"{script.stem}.exe"
            )

    else:

        exe_path = (
            output_directory
            / f"{script.stem}.exe"
        )

    # --------------------------------------------------------
    # Successful build
    # --------------------------------------------------------

    print()
    print("=" * 60)
    print("BUILD COMPLETE")
    print("=" * 60)
    print()

    if exe_path.exists():

        size_mb = (
            exe_path.stat().st_size
            / (1024 * 1024)
        )

        print(
            "EXE created successfully!"
        )

        print()

        print(
            f"  {exe_path}"
        )

        print()

        print(
            f"Size: {size_mb:.2f} MB"
        )

        # Final interaction.
        # The builder exits immediately afterwards.
        ask_open_output_directory(
            output_directory
        )

    else:

        print(
            "The build command completed, but the"
        )

        print(
            "expected EXE could not be found."
        )

        print()

        print("Expected:")
        print(
            f"  {exe_path}"
        )

        pause()


# ============================================================
# Main
# ============================================================

def main():

    clear_screen()

    print(
        "Universal Python EXE Builder"
    )

    print(
        "=" * 60
    )

    print()

    print(
        "Builder location:"
    )

    print(
        f"  {APP_DIR}"
    )

    print()

    if not is_frozen():

        print(
            "What would you like to do?"
        )

        print()

        print(
            "  1. Build a Python script"
        )

        print(
            "  2. Build the EXE Builder itself"
        )

        print()

        while True:

            choice = clean_input(
                input(
                    "Select an option [1]: "
                )
            )

            if not choice or choice == "1":

                build_normal_script()

                return

            if choice == "2":

                build_builder()

                return

            print(
                "Please enter 1 or 2."
            )

    else:

        build_normal_script()


# ============================================================
# Entry point
# ============================================================

if __name__ == "__main__":
    main()