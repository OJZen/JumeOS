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
inline bool systemChord(uint32_t keys) { return (keys & Chord)==Chord || ((keys&Select)&&(keys&(Start|X|Y))); }
struct Sample {
    uint32_t keys = 0;
    std::array<int32_t, 4> axes{};
    bool operator==(const Sample &other) const { return keys == other.keys && axes == other.axes; }
    bool operator!=(const Sample &other) const { return !(*this == other); }
};

// Only stick clicks wait for the chord window; ordinary controls are immediate.
// A short standalone click is emitted before its release, rather than discarded.
struct Policy {
    explicit Policy(int milliseconds) : chordMs(milliseconds) {}
    int chordMs;
    uint32_t mode = Ui, pending = 0;
    int64_t deadline = 0;
    bool waiting = true, ownerPending = false, chordSpent = false;
    uint32_t previous = 0, shortcut = 0;
    int64_t heldAt = 0;
    bool selecting = false, shortcutSpent = false;
    void setMode(uint32_t next) {
        mode = next; waiting = true; ownerPending = false;
        pending = 0; deadline = 0; chordSpent = false;
        previous=shortcut=0;selecting=shortcutSpent=false;heldAt=0;
    }
    template<class Emit, class Request>
    void update(const Sample &input, bool neutral, int64_t now, Emit deliver, Request request) {
        if (ownerPending) return;
        if (waiting) {
            if (!neutral) return;
            waiting = false;
        }
        auto output = input;
        // Select is a modifier: defer its standalone press until release. Face
        // buttons stay immediate; a shortcut requires Select first or simultaneous.
        if(input.keys&Select) {
            if(!selecting){selecting=true;shortcutSpent=false;shortcut=0;}
            const auto pressed=(input.keys&~previous)&(Start|X|Y);
            if(!shortcut&&!shortcutSpent&&pressed) {
                shortcut=(pressed&Start)?Start:(pressed&Y)?Y:X;heldAt=now;
                if(shortcut!=Start){shortcutSpent=true;ownerPending=true;waiting=true;request(shortcut==Y?Tasks:Close);previous=input.keys;return;}
            }
            output.keys&=~Select;
            if(shortcut)output.keys&=~(Start|X|Y);
            if(shortcut==Start&&!shortcutSpent) {
                if(!(input.keys&Start)){shortcutSpent=true;ownerPending=true;waiting=true;request(Home);previous=input.keys;return;}
                if(now-heldAt>=2000){shortcutSpent=true;ownerPending=true;waiting=true;request(Kill);previous=input.keys;return;}
            }
        } else if(selecting) {
            selecting=false;
            if(shortcut==Start&&!shortcutSpent){shortcutSpent=true;ownerPending=true;waiting=true;request(Home);previous=input.keys;return;}
            if(!shortcutSpent&&!shortcut){auto pulse=output;pulse.keys|=Select;deliver(pulse);}
            shortcut=0;
        }
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
