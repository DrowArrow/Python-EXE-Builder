# Python-EXE-Builder
a vibe coded python script designed to package your python script into an .exe file

## Requirements
you need one or both of the following installed to use this script
- PyInstaller
- py2exe

## Introduction

the purpose of this tool is to simplify turning `.py` scripts into `.exe` files.

I wanted to automate the process of making an `.exe` version of any `.py` script without having to make personalised setup.py scripts for each one. and this is the result.

There are some checks done during the process:
- The tool will try to identify any and all modules needed for the script
- If any modules are missing, it will offer to install them before proceeding with building the .exe
- You can choose to have the `.exe` file compiled to either launch with or without a console window.
- can make a compiled version of the build.py to provide you with an `.exe` version of the build tool

