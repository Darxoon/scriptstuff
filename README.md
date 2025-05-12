# scriptstuff

Sticker Star KSM tool

## NOTE: This tool has been superseded and is no longer developed. Check out [Longboost's gibberish](https://github.com/Longboost/gibberish) instead.

## Usage

You need [Python 3](https://www.python.org/) and and a dump of Sticker Star's romfs.

Clone scriptstuff and open its directory in a terminal or command prompt. Run one of the following commands:

### Windows

    py main.py <input file.bin | input file.yaml>

### Mac / Linux

    python3 main.py <input file.bin | input file.yaml>

Where `input file.bin` refers to the binary KSM file you want to disassemble. This will produce a yaml file.

To reassemble the yaml file (which is not yet supported), simply pass the .yaml file as `input file.yaml` instead.
