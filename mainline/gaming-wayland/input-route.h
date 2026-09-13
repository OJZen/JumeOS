#pragma once
#include <array>
#include <cstdint>

namespace Route {
// Local inherited SOCK_SEQPACKET channel. No filesystem socket or network service.
constexpr uint32_t Version = 2, Ui = 0, Game = 1;
enum Type : uint32_t { Mode = 1, Ready, State, Panel, Ack, Inject, CancelInject, InjectDone, InjectDenied };
enum Flag : uint32_t { WaitingNeutral = 1, WaitingOwner = 2, InjectionCancelled = 4 };
constexpr const char *ButtonNames[] = {"b", "a", "x", "y", "l1", "r1", "l2", "r2", "select", "start", "up", "down", "left", "right", "l3", "r3"};
struct Packet {
    uint32_t version = Version, type = 0;
    uint64_t sequence = 0;
    uint32_t mode = Ui, flags = 0, keys = 0; // Inject command: flags is duration in ms (10..1000).
    int32_t axes[4]{}; // UI samples normalized to -32767..32767; no deadzone applied.
    char device[32]{}; // Ready only: UI_GET_SYSNAME of the routed virtual gamepad.
    uint32_t reserved = 0;
};
static_assert(sizeof(Packet) == 80, "local packet ABI changed");
constexpr uint32_t L3 = 1U << 14, R3 = 1U << 15, Chord = L3 | R3;
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
    void setMode(uint32_t next) {
        mode = next; waiting = true; ownerPending = false;
        pending = 0; deadline = 0; chordSpent = false;
    }
    template<class Emit, class Request>
    void update(const Sample &input, bool neutral, int64_t now, Emit deliver, Request request) {
        if (ownerPending) return;
        if (waiting) {
            if (!neutral) return;
            waiting = false;
        }
        auto output = input;
        const auto clicks = input.keys & Chord;
        if (!chordSpent && !pending && clicks) {
            pending = clicks; deadline = now + chordMs;
        }
        if (!chordSpent && pending) {
            if (clicks == Chord && now <= deadline) {
                pending = 0; deadline = 0; ownerPending = true; waiting = true;
                request(); return;
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
