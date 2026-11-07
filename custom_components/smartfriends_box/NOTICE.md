# RolloFriends — notices

This directory is part of **RolloFriends**, an independent Home Assistant
integration for the SmartFriends Box. It is licensed under the MIT License,
reproduced below so that a manual installation copying only this directory
keeps the license and attribution.

## Protocol references

- [`LoPablo/smartFriendsApi`](https://github.com/LoPablo/smartFriendsApi)
  (ISC, Copyright 2020 Pascâl Hartmann) was used as a protocol reference for the
  box port, TLS CA, digest order, `helo`/`login`/`getAllNewInfos`/
  `setDeviceValue`, and newline framing.
- [`GimpArm/smartfriends-bridge`](https://github.com/GimpArm/smartfriends-bridge)
  (GPL-3.0) was used only as a behavioral reference for the observed message
  structure, master/component grouping, command values, and the position
  inversion used by its MQTT template. No code was copied or translated.

This integration bundles a byte-identical copy of the `aiosmartfriends` library
under `vendor/aiosmartfriends`. The same notices apply to that copy.

## Trust anchor

`vendor/aiosmartfriends/certs/enexoma-root2.pem` is the public Enexoma root
certificate used to verify the SmartFriends Box. It is a trust anchor, not
application code.

- Subject/Issuer: `CN=enexoma-root2, O=enexoma AG`
- Validity: 2016-10-27 to 2036-10-27
- SHA-256 fingerprint:
  `E1:15:BE:FD:D2:F0:9A:BA:64:A6:09:E9:6A:4C:8A:63:7D:7C:3B:4B:11:3E:EF:C0:35:49:EF:60:8F:76:D5:C1`

The certificate is verified at runtime and the connection fails closed if the
fingerprint changes.

## Trademarks

SmartFriends, Schellenberg, Rollodrive, and Enexoma are trademarks of their
respective owners. This project is not affiliated with or endorsed by them.

## MIT License

Copyright (c) 2026 RolloFriends contributors

Permission is hereby granted, free of charge, to any person obtaining a copy of
this software and associated documentation files (the "Software"), to deal in
the Software without restriction, including without limitation the rights to
use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of
the Software, and to permit persons to whom the Software is furnished to do so,
subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
