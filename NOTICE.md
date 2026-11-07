# Third-party notices

RolloFriends is an independent implementation. It contains no source code from
the GPL-licensed `GimpArm/smartfriends-bridge` project.

## Protocol references

- `LoPablo/smartFriendsApi` (ISC, Copyright 2020 Pascâl Hartmann) was used as a
  protocol reference for port, TLS CA, digest order, `helo`/`login`/
  `getAllNewInfos`/`setDeviceValue`, and newline framing.
- `GimpArm/smartfriends-bridge` (GPL-3.0) was used only as a behavioral
  reference for the observed message structure, master/component grouping,
  command values, and the position inversion used by its MQTT template. No code
  was copied or translated.

## Trust anchor

`src/aiosmartfriends/certs/enexoma-root2.pem` is the public Enexoma root
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
