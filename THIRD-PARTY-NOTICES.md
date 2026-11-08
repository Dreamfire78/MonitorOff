# Third-party notices

MonitorOff includes or is built with the following third-party components.

## Boxicons – icon "monitor"

`monitor_icon.svg` and the `.ico` files generated from it are based on the icon
[`monitor`](https://icon-sets.iconify.design/boxicons/monitor/) from
[Boxicons](https://github.com/box-icons/boxicons-core) (obtained via [Iconify](https://iconify.design/)),
recolored for the program and tray icons.

```
MIT License

Copyright (c) 2026 Boxicons

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## Python

The released `MonitorOff.exe` bundles the Python runtime and parts of its standard library,
licensed under the [Python Software Foundation License](https://docs.python.org/3/license.html).
Copyright (c) 2001 Python Software Foundation. All rights reserved.

## PyInstaller

The exe is built with [PyInstaller](https://pyinstaller.org/). Its bootloader is licensed under the
GPL 2.0 with a special exception that allows distributing the resulting executables under any license
([details](https://github.com/pyinstaller/pyinstaller/blob/develop/COPYING.txt)).

## Build-only tools

[PyMuPDF](https://github.com/pymupdf/PyMuPDF) and [Pillow](https://github.com/python-pillow/Pillow)
are used only to render the icons at build time and are not part of the distributed exe.
