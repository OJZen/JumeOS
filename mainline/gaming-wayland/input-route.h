#pragma once
#include <array>
#include <cstdint>

namespace Route {
// Local inherited SOCK_SEQPACKET channel. No filesystem socket or network service.
constexpr uint32_t Version = 3, Ui = 0, Game = 1, Slots = 4;
enum Type : uint32_t { Mode = 1, Ready, State, Panel, Ack, Inject, CancelInject, InjectDone, InjectDenied, Tasks, Home, Close, Kill, Hold };
enum Flag : uint32_t { WaitingNeutral = 1, WaitingOwner = 2, InjectionCancelled = 4 };
constexpr const char *ButtonNames[] = {"b", "a", "x", "y", "l1", "r1", "l2", "r2", "select", "start", "up", "down", "left", "right", "l3", "r3"};
struct Packet {
    uint32_t version = Version, type = 0;
    uint64_t sequence = 0;
    uint32_t mode = Ui, flags = 0, keys = 0; // Inject command: flags is duration in ms (10..1000).
    int32_t axes[4]{}; // UI samples normalized to -32767..32767; no deadzone applied.
    char device[32]{}; // Ready only: UI_GET_SYSNAME of the routed virtual gamepad.
    uint32_t reserved = 0; // Per-application input slot; never broadcast to other tasks.
};
static_assert(sizeof(Packet) == 80, "local packet ABI changed");
constexpr uint32_t L3 = 1U << 14, R3 = 1U << 15, Chord = L3 | R3;
constexpr uint32_t Select = 1U << 8, Start = 1U << 9, X = 1U << 2, Y = 1U << 3;
inline bool systemChord(uint32_t keys) { return (keys & Chord)==Chord || ((keys&Select)&&(keys&(Start|Y))); }
struct Sample {
    uint32_t keys = 0;
    std::array<int32_t, 4> axes{};
    bool operator==(const Sample &other) const { return keys == other.keys && axes == other.axes; }
    bool operator!=(const Sample &other) const { return !(*this == other); }
};

// Only stick clicks wait for the chord window; ordinary controls are immediate.
// A short standalone click is emitted before its release, rather than discarded.
// Select (§7.2, §7.5) is the system modifier: with Start (short = Home, 2 s = Kill) or Y (Tasks),
// pressed after Select or up to the chord window before it. A lone Select is judged on release.
// In a game, Select with any other key, or held 600 ms without a shortcut, goes to the game at
// once (press first, then the other key) and ends shortcut judgement until it is released.
// On the desktop Select with another key does nothing.
constexpr int64_t SelectPassMs = 600, KillMs = 2000;
struct Policy {
    explicit Policy(int milliseconds) : chordMs(milliseconds) {}
    int chordMs;
    uint32_t mode = Ui, pending = 0;
    int64_t deadline = 0;
    bool waiting = true, ownerPending = false, chordSpent = false;
    uint32_t previous = 0, shortcut = 0, swallowed = 0;
    int64_t heldAt = 0, selectAt = 0, startAt = -1, yAt = -1;
    bool selecting = false, shortcutSpent = false, selectPassed = false;
    void setMode(uint32_t next) {
        mode = next; waiting = true; ownerPending = false;
        pending = 0; deadline = 0; chordSpent = false;
        previous=shortcut=swallowed=0;selecting=shortcutSpent=selectPassed=false;heldAt=selectAt=0;startAt=yAt=-1;
    }
    template<class Emit, class Request>
    void update(const Sample &input, bool neutral, int64_t now, Emit deliver, Request request) {
        if (ownerPending) return;
        if (waiting) {
            if (!neutral) return;
            waiting = false;
        }
        auto output = input;
        const auto fresh = input.keys & ~previous;
        if (fresh & Start) startAt = now;
        if (fresh & Y) yAt = now;
        auto requestNow = [&](uint32_t action) {
            shortcutSpent = true; ownerPending = true; waiting = true; request(action); previous = input.keys;
        };
        if(input.keys&Select) {
            auto pressed = fresh & (Start|Y);
            if(!selecting) {
                selecting=true;shortcutSpent=selectPassed=false;shortcut=0;selectAt=now;
                // Start or Y pressed just before Select still makes the shortcut.
                if ((input.keys & Start) && startAt >= 0 && now - startAt <= chordMs) pressed |= Start;
                if ((input.keys & Y) && yAt >= 0 && now - yAt <= chordMs) pressed |= Y;
            }
            const auto others = fresh & ~(Select|Start|Y);
            if(!shortcut&&!shortcutSpent&&!selectPassed&&pressed) {
                shortcut=(pressed&Start)?Start:Y;heldAt=now;
                if(shortcut==Y){requestNow(Tasks);return;}
            } else if(!shortcut&&!shortcutSpent&&!selectPassed&&mode==Game&&(others||now-selectAt>=SelectPassMs)) {
                selectPassed=true;
                if(others){auto press=input;press.keys&=~others;deliver(press);}
            }
            // Desktop: keys pressed with Select (other than its shortcut) do nothing, nor does the release.
            if(mode==Ui){swallowed|=fresh&~(Select|shortcut);if(others&&!shortcut)shortcutSpent=true;}
            if(!selectPassed)output.keys&=~Select;
            if(shortcut)output.keys&=~(Start|Y);
            if(shortcut==Start&&!shortcutSpent) {
                if(!(input.keys&Start)){requestNow(Home);return;}
                if(now-heldAt>=KillMs){requestNow(Kill);return;}
            }
        } else if(selecting) {
            selecting=false;
            if(shortcut==Start&&!shortcutSpent){requestNow(Home);return;}
            if(!shortcutSpent&&!shortcut&&!selectPassed){auto pulse=output;pulse.keys|=Select;deliver(pulse);}
            shortcut=0;selectPassed=false;
        }
        swallowed&=input.keys;output.keys&=~swallowed;
        previous=input.keys;
        const auto clicks = input.keys & Chord;
        if (!chordSpent && !pending && clicks) {
            pending = clicks; deadline = now + chordMs;
        }
        if (!chordSpent && pending) {
            if (clicks == Chord && now <= deadline) {
                pending = 0; deadline = 0; ownerPending = true; waiting = true;
                request(Panel); return;
            }
            if (now >= deadline || !(clicks & pending)) {
                // Preserve a press/release completed between polls or before the deadline.
                if (!(clicks & pending)) { auto pulse = input; pulse.keys |= pending; deliver(pulse); }
                pending = 0; deadline = 0; chordSpent = true;
            } else output.keys &= ~Chord;
        }
        deliver(output);
        if (!clicks) chordSpent = false;
    }
};
}
