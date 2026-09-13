# R46H guarded remote input v0.1

Status: **BASE PASS / V0.16 10 MS DEVICE PASS**

This p2-only overlay extends the already accepted strict screenshot SSH key with
16 fixed ES-DE keyboard actions. It does not open a port, run a daemon, replace
the permanent P1 gamepad, restart the frontend or modify BOOT, p1 or p3.

The one-shot helper creates `R46H Remote Keyboard`, emits one bounded 100 ms key
pulse and removes the device. Its logical actions follow ES-DE 3.4.1 defaults:

```text
up down left right  a b x y  select start  l1 r1 l2 r2 l3 r3
```

On p2 v0.15, repeated screenshot checks showed that 100 ms can cross ES-DE's
repeat threshold and skip entries. A temporary 10 ms binary produced exact
single steps. The reproducible p2 v0.16 builder compiled that exact binary. Its
two-readback media proof, target self-test and exact screenshot-verified
right/left single-step roundtrip passed on 2026-09-05.

The existing forced-command key accepts only `r46h-input ACTION` plus the three
existing screenshot operations. Sudo authorizes each complete helper command;
there is no wildcard action, raw evdev code, arbitrary duration or shell input.

## Build and deploy

```sh
mainline/gaming-remote-input/build-payload.sh
PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -B \
  mainline/tests/test-r46h-gaming-remote-input.py -v
```

That command preserves the historical standalone v0.1/100 ms payload. P2 v0.16
uses the same source with the fixed `KEY_HOLD_MILLISECONDS=10` build parameter;
do not replay the old overlay installer on the consolidated image.

Stage the seven payload files as root-owned mode 0600 under the root-owned mode
0700 directory `/run/r46h-gaming-remote-input-v0.1`, then pass the exact staged
installer SHA-256 to `install.sh`. The transaction verifies the accepted ES-DE
and remote-screen receipts, preserves the previous SSH gateway and sudo policy,
and leaves the running ES-DE/RetroArch PID and restart count unchanged.

With the existing forced-command remote-screen key and serial-verified host
key, send one action:

```sh
ssh -F /dev/null \
  -i mainline/out/.cache/r46h-remote-screen/client/id_ed25519 \
  -o BatchMode=yes -o IdentitiesOnly=yes \
  -o PreferredAuthentications=publickey -o PasswordAuthentication=no \
  -o KbdInteractiveAuthentication=no -o NumberOfPasswordPrompts=0 \
  -o StrictHostKeyChecking=yes \
  -o UserKnownHostsFile=mainline/out/.cache/r46h-es-de/ssh/known_hosts \
  -o HostKeyAlgorithms=ssh-ed25519 -o UpdateHostKeys=no \
  -o ClearAllForwardings=yes -T ark@R46H_IPV4 'r46h-input down'
```

Acceptance is one remote D-pad move, A selection and B return observed through
strict screenshots, followed by physical D-pad/A confirmation, unchanged
frontend PID/restarts, read-only `/roms`, zero ext4 errors and no failed units.
Run `sudo /usr/local/sbin/r46h-remote-input-rollback` for byte-exact restoration.

This first version intentionally controls frontend/menu navigation only. It does
not synthesize analog axes or claim gameplay input; physical controls remain the
authority for controller and gameplay acceptance.
